#!/usr/local/python/bin/python
"""
TODO: Add docstring
"""
import os
import sys
import logging
import argparse as ap
import glob as g
from datetime import (
    datetime,
    timedelta
    )
import pymysql
import numpy as np
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

def make_montage(movie_dir, das_list, start_id):
    """
    sync the pngs according to earliest image that day then
    montage all the pngs with imagemagick
    """
    logging.info("{} - Making montage".format(nowstr()))
    os.chdir(movie_dir)
    logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))

    t_refs, imlens = [], []

    # scan all folders looking for earliest image of the night
    n_images = 0
    for das in das_list:
        os.chdir(das)
        logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
        t = sorted(g.glob('*.png'))
        if not t:
            os.chdir('../')
            logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
            continue
        t_refs.append(getDatetime(t[0]))
        imlens.append(len(t))
        n_images += len(t)
        os.chdir('../')
        logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
    # check for no data exit if so
    if not n_images:
        logging.fatal("{} - No pngs found, exiting...".format(nowstr()))
        sys.exit(1)
    # list of earliest times per camera and length of imaging run
    t_refs = np.array(t_refs)
    imlens = np.array(imlens)
    # now work out which was the earliest and go there to start the time series
    n = np.where(t_refs == min(t_refs))[0]
    if len(n) > 1:
        n = n[0]
    logging.info("{} - Reference DAS machine: {}".format(nowstr(), das_list[n]))
    # start in earliest folder and generate a list of reference times
    os.chdir(das_list[n])
    logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
    # reset t_refs for start_id calculations
    t = sorted(g.glob('*.png'))
    t_refs = []
    for i in range(0, len(t)):
        t_refs.append(getDatetime(t[i]))
    os.chdir('../')
    logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))

    # now go through each other dir and generate their starting points
    for das in das_list:
        os.chdir(das)
        logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
        t = sorted(g.glob('*.png'))
        if not t:
            os.chdir('../')
            logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
            continue
        x = getDatetime(t[0])
        diff = []
        for j in range(0, len(t_refs)):
            diff.append(abs((t_refs[j] - x).total_seconds()))
        z = diff.index(min(diff))
        start_id[das] = z
        os.chdir('../')
        logging.info("{} - Moving to: {}".format(nowstr(), os.getcwd()))
    logging.info("{} - Dictionary of start_ids:".format(nowstr()))
    logging.info(start_id)

    # work out the new video size for non time overlapping images
    max_start = 0
    for i in start_id:
        if start_id[i] > max_start:
            max_start = start_id[i]
    run_len = int(max(imlens) + max_start)

    # montage based on start_ids
    # keep a dictionary of the directory contents from
    # first glob as to not check each time we loop around...
    t = {das: [] for das in das_list}

    for i in range(0, run_len):
        files = ""
        for das in das_list:
            if i == 0:
                t[das].append(sorted(g.glob('{}/*.png'.format(das))))

            if start_id[das] == -1 or i < start_id[das]:
                files = files + "empty/empty.png "
            else:
                try:
                    files = files + t[das][0][i - start_id[das]] + " "
                except IndexError:
                    files = files + "empty/empty.png "

        logging.info("{} - [{}/{}] {}".format(nowstr(), i+1, run_len, files))

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
    v_id = os.popen("/usr/local/python/bin/python " \
                    "/usr/local/cron/scripts/upload2youtube.py " \
                    "--file={} --title={} --description='NGTS Daily Movie'" \
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
    start_id = {key: -1 for key in das_list}
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
        make_montage(movie_dir, das_list, start_id)
    # make movie of montages and tidy up
    if args.movie:
        # set up the movie outpout name
        movie_name = "{}/daily_movies/movie_{}.mp4".format(movie_dir, night)
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
