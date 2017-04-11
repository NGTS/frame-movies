#!/usr/local/python/bin/python
"""
grab all the actions from 1 day ago, split according to camera
go to last action and get the last image
only make pngs and upload to webserver if needed
"""
import os
import sys
import glob as g
from datetime import datetime
import pymysql
from create_movie import create_movie

# pylint: disable = invalid-name
# pylint: disable = redefined-outer-name
# pylint: disable = superfluous-parens

# globals
topdir = "/ngts"
convert_loc = "/usr/local/bin"
cron_dir = "/usr/local/cron/work"
web_dir = "/ngts/staging/archive/last_images"
thumbsize = 15 # scaling percentage

# empty dictionary for the actions for each camera
cams = {801:None, 802:None, 803:None, 804:None,
        805:None, 806:None, 807:None, 808:None,
        809:None, 810:None, 811:None, 812:None,
        813:None, 899:None}

# cam/das map
das = {801:None, 802:None, 803:None,
       804:None, 805:None, 806:None,
       807:None, 808:None, 809:None,
       810:None, 811:None, 812:None,
       813:None, 899:None}

def getDasLoc(das):
    for i in das:
        if i != 899:
            comm = '/usr/local/paladin/bin/ngwhereis %d' % (i)
            s = os.popen(comm).readline()
            try:
                das[i] = s.split()[0]
            except IndexError:
                das[i] = None
            print(s)
    return das

def checkDasMachinesAreOnline(das):
    cont = 0
    for i in das:
        if das[i]:
            x = os.popen('ping -w 0.2 -c 1 %s' % (das[i])).readlines()
            if ' 0% packet loss' in x[-2]:
                cont += 0
            else:
                cont += 1
    if cont > 0:
        print("MACHINES ARE DOWN - ignoring image generation (NFS issues)")
        sys.exit(1)

def getLastActionIds(cams):
    for cam in cams:
        with pymysql.connect(host='ds', db='ngts_ops') as cur:
            qry = """
                SELECT
                ril.camera_id, ril.action_id, al.action
                FROM raw_image_list AS ril
                LEFT JOIN action_list AS al
                USING (action_id)
                WHERE ril.camera_id={}
                AND ril.start_time_utc >= now() - INTERVAL 1 HOUR
                ORDER BY ril.start_time_utc DESC LIMIT 1
                """.format(cam)
            print(qry)
            t1 = datetime.utcnow()
            cur.execute(qry)
            t2 = datetime.utcnow()
            print('Query took: {:.2f}s'.format((t2-t1).total_seconds()))
            # get the action ids for each camera (and dome 899)
            qry_result = cur.fetchone()
            if qry_result is not None:
                cams[int(qry_result[0])] = "action{}_{}".format(qry_result[1],
                                                                qry_result[2])
    return cams

def makePngImages(cron_dir, web_dir, cam, thumbsize):
    # get the last image
    t = sorted(g.glob('*.fits'))
    if len(t) > 0:
        pngfile = "%s.png" % (t[-1])
        print("PNG file to make is {}.png".format(t[-1]))
        if pngfile not in os.listdir('{}/last_imgs/{}/'.format(cron_dir, cam)):
            create_movie([t[-1]],
                         images_directory='{}/last_imgs/{}'.format(cron_dir, cam),
                         no_time_series=True,
                         include_increment=False,
                         clobber_images_directory=False,
                         resize_factor=4,
                         multiprocess=False)
            here = os.getcwd()
            os.chdir("{}/last_imgs/{}".format(cron_dir, cam))
            print("Moving to {}/last_imgs/{}".format(cron_dir, cam))
            # make a thumbnail
            thumbfile = "{:s}.{:.2f}.png".format(t[-1], (thumbsize/100.))
            os.system('/usr/local/bin/convert %s -resize %d%% %s' % (pngfile,
                                                                     thumbsize,
                                                                     thumbfile))
            print("Making thumbnail {} --> {}".format(pngfile, thumbfile))
            # rescale the png to make it smaller
            os.system('/usr/local/bin/convert %s -resize 50%% %s' % (pngfile, pngfile))
            print("Rescaling larger image %s by 50%%" % (pngfile))
            try:
                f = open('last_img.log').readline()
            except IOError:
                f = "XXX"
            print("Last image: {}".format(f))
            if f != pngfile:
                os.system('cp {} {}/cam_{}.png'.format(pngfile, web_dir, cam))
                print("Copying {} to {}/cam_{}.png".format(pngfile, web_dir, cam))
                os.system('cp {} {}/cam_{}_s.png'.format(thumbfile, web_dir, cam))
                print("Copying {} to {}/cam_{}_s.png".format(thumbfile, web_dir, cam))
                f3 = open('last_img.log', 'w')
                f3.write(pngfile)
                f3.close()
                print('last_img.log updated with {}'.format(pngfile))
            else:
                print("Last image already up to date, skipping...")
                print('Last image up to date')
            os.chdir(here)
            print('Moving to {}'.format(here))
        else:
            print('{} exists already, skipping...'.format(pngfile))
    else:
        print("No new fits images to convert, skipping {}...".format(das[cam]))

if __name__ == "__main__":
    # get the location of each camera/das
    das = getDasLoc(das)
    # check das machines are all online
    checkDasMachinesAreOnline(das)
    # get a list of last actions for each camera
    cams = getLastActionIds(cams)
    # now go into the top level directory
    os.chdir(topdir)
    # loop over each camera and make the pngs
    for cam in cams:
        if cams[cam] is not None and cam != 899 and das[cam] is not None:
            try:
                os.chdir("{}/{}".format(das[cam], cams[cam]))
                print("Moving to {}/{}".format(das[cam], cams[cam]))
            except OSError:
                print('Folder {}/{} does not exist, skipping...'.format(das[cam], cams[cam]))
                continue
            makePngImages(cron_dir, web_dir, cam, thumbsize)
            os.chdir(topdir)
            print('Moving to {}'.format(topdir))
