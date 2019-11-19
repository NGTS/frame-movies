#!/usr/local/python/bin/python
"""
TODO: Add docstring
"""
import os
import sys
import logging
import argparse as ap
import glob as g
from collections import OrderedDict
from datetime import (
    datetime,
    timedelta
    )
import pymysql
from create_movie import (
    create_movie,
    generate_movie
    )

# pylint: disable=logging-format-interpolation
# pylint: disable=invalid-name
# pylint: disable=redefined-outer-name

movie_dir = "/ngts/staging/archive/movie"
logfile = "/ngts/staging/archive/logs/movie/"
logging.basicConfig(filename=logfile,
                    level=logging.DEBUG,
                    format='%(levelname)10s - %(message)s')

def argParse():
    """
    TODO: Add docstring
    """
    p = ap.ArgumentParser()
    p.add_argument("--pngs",
                   help="make the PNG files for a given das",
                   choices=getDasList())
    p.add_argument("--montage",
                   help="montage all PNG files",
                   action="store_true")
    p.add_argument("--movie",
                   help="make movie from montaged PNG files",
                   action="store_true")
    p.add_argument("--tidy",
                   help="tidy up pngs?",
                   action="store_true")
    p.add_argument("--upload",
                   help="upload movie to YouTube",
                   action="store_true")
    return p.parse_args()

def getDasList():
    """
    Generate a list of das machine names
    """
    return ["das{:02d}".format(i) for i in range(1, 13)]

def getLastNight():
    """
    Get the night int for last night
    """
    tnow = datetime.utcnow()
    if tnow.hour < 18:
        delta = -1
    else:
        delta = 0
    return int((tnow + delta*timedelta(days=1)).strftime('%Y%m%d'))

def getActionsToProcess(night):
    """
    Find all last night's actions
    """
    actions_to_process = []
    with pymysql.connect(host='ds', db='ngts_ops') as cur:
        qry = """
            SELECT
            action_id, action
            FROM action_list
            WHERE night=%s
            AND camera_id != 899
            AND action != 'stow'
            AND action != 'roofopen'
            """
        qry_args = (night,)
        cur.execute(qry, qry_args)
        results = cur.fetchall()
        for row in results:
            actions_to_process.append("action{}_{}".format(row[0], row[1]))
    return actions_to_process

def make_pngs(movie_dir, actions, das_id):
    """
    Take a list of actions and make pngs
    for the local items. The output is stored in

    /movie_dir/das_id/
    """
    logging.info("{} - Making pngs from {}".format(nowstr(), das_id))
    # now loop over the night's actions
    # only make the pngs for the local images
    for action in actions:
        if os.path.exists("/local/{}".format(action)):
            logging.info("{} - Making pngs from {}".format(nowstr(), action))
            imglist = sorted(g.glob("/local/{}/*.fits".format(action)))
            if imglist:
                das_movie_dir = "{}/{}".format(movie_dir, das_id)
                create_movie(imglist,
                             images_directory=das_movie_dir,
                             include_increment=False,
                             clobber_images_directory=False,
                             resize_factor=4)

def getDatetime(t):
    """
    get the date and time from a raw image filename
    and create a datetime variable
    """
    ychk = int(t[8:12])
    mthchk = int(t[12:14])
    dchk = int(t[14:16])
    hchk = int(t[16:18])
    minchk = int(t[18:20])
    schk = int(t[20:22])
    x = datetime(year=ychk, month=mthchk,
                 day=dchk, hour=hchk,
                 minute=minchk, second=schk)
    return x

def make_montage(movie_dir, das_list):
    """
    sync the pngs according to earliest image that day then
    montage all the pngs with imagemagick
    """
    logging.info("{} - Making montage".format(nowstr()))
    os.chdir(movie_dir)
    logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))

    # just get a list of all the images for all das machines
    # we don't care about syncing them in time as its annoying and I
    # don't have time to fix this now.
    images = OrderedDict()
    for das in das_list:
        images[das] = g.glob('{}/*.png'.format(das))

    # get the das machine with the max number of images
    max_images = 0
    for das in das_list:
        if len(images[das]) > max_images:
            max_images = len(images[das])

    # now loop max_images times
    # grab an image from each das machine
    # if that list gives an IndexError, fill
    # it with a blank image
    for i in range(0, max_images):
        files = ""
        for das in das_list:
            try:
                files += "{} ".format(images[das][i])
            except IndexError:
                files += "empty/empty.png "

        logging.info("{} - [{}/{}] {}".format(nowstr(), i+1, max_images, files))

        # now montage them together
        comm = "/usr/local/bin/montage {} -tile 6x2 -geometry " \
               "400x300-80+3 tiled_{:05d}.png".format(files, i)
        logging.info("{} - {}".format(nowstr(), comm))
        os.system(comm)

def make_movie(movie_dir, movie):
    """
    Make a movie of the montaged images
    """
    tiled_list = sorted(g.glob("{}/tiled*.png".format(movie_dir)))
    if tiled_list:
        logging.info("{} - Making movie".format(nowstr()))
        generate_movie(movie_dir, movie)
    else:
        logging.info("{} - No tiled images, skipping".format(nowstr()))
        sys.exit(1)

def upload2youtube(filename, title):
    """
    Upload the movie to YouTube using the OAuth setup for NGTS-OPS user channel
    """
    logging.info("{} - Uploading video to YouTube".format(nowstr()))
    v_id = os.popen("/usr/local/anaconda3/bin/python " \
                    "/usr/local/cron/scripts/upload2youtube.py " \
                    "--file={} --title={} --description='NGTS Daily Movie' " \
                    "--category='22' " \
                    "--privacyStatus='unlisted'".format(filename, title)).readlines()
    video_id = v_id[1].split()[2].replace("'", "")
    logging.info("{} - Video ID: {}".format(nowstr(), video_id))
    return video_id

def logVideoId(video_id, night):
    """
    Log the video ID to the database
    """
    qry = """
        INSERT INTO daily_movies
        (night, youtube_id)
        VALUES (%s, %s)
        """
    qry_args = (night, video_id,)
    with pymysql.connect(host='ds', db='ngts_ops') as cur:
        cur.execute(qry, qry_args)
    logging.info("{} - Logging video ID".format(nowstr()))
    logging.info("{} - {}".format(nowstr(), qry))

def nowstr():
    """
    TODO: Add docstring
    """
    return datetime.utcnow().replace(microsecond=0).isoformat()

if __name__ == "__main__":
    # get time of start
    t1 = datetime.utcnow()
    # parse command line
    args = argParse()
    # get a list of das machines
    das_list = getDasList()
    # start id for movie
    #start_id = {key: -1 for key in das_list}
    # get last night
    night = getLastNight()
    # check the move dir exists
    if not os.path.exists(movie_dir):
        os.mkdir(movie_dir)
    # make pngs
    if args.pngs:
        actions = getActionsToProcess(night)
        make_pngs(movie_dir, actions, args.pngs)
    # montage pngs
    if args.montage:
        #make_montage(movie_dir, das_list, start_id)
        make_montage(movie_dir, das_list)
    # set up the movie outpout name
    movie_name = "{}/daily_movies/movie_{}.mp4".format(movie_dir, night)
    # make movie of montages and tidy up
    if args.movie:
        make_movie(movie_dir, movie_name)
        # check tge movie exists before wiping the pngs
        if not os.path.exists(movie_name):
            logging.fatal("{} - NO MOVIE FILE! QUITTING".format(nowstr()))
            # TODO : send an email here!
            sys.exit(1)
        # clean up the pngs
        if args.tidy and os.path.exists(movie_name):
            logging.info("{} - Removing tiled pngs".format(nowstr()))
            os.system("/bin/rm {}/tiled*.png".format(movie_dir))
            for das in das_list:
                logging.info("{} - Removing individual pngs".format(nowstr()))
                os.system("/bin/rm %s/%s/IMAGE*.png" % (movie_dir, das))
    # upload to youtube
    if args.upload and os.path.exists(movie_name):
        if os.path.exists(movie_name):
            video_id = upload2youtube(movie_name, night)
            logVideoId(video_id, night)
        else:
            logging.fatal("{} - No such movie file: {}".format(nowstr(), movie_name))
    # some final stats
    t2 = datetime.utcnow()
    dt = (t2-t1).total_seconds()/60.
    logging.info("{} - Runtime: {:.2f} mins".format(nowstr(), dt))
