#!/usr/local/python/bin/python
# script to check the previously unsolved files
#
# to do:
#   Sanity check all the image_ids in the table actually have a png
#   quick check shows 1349 in DB and 1353 pngs, 4 out, not bad
#

import os,sys,getpass,time
import glob as g
from astropy.io import fits
from collections import defaultdict
from ds9 import *
import argparse as ap

me=getpass.getuser()
if me=='ops':
    w_dir="/ngts/staging/archive/minisurvey/junk"
    astrom_loc="/usr/local/astrometry.net/bin/"
elif me=='James':
    w_dir='/Users/James/Desktop/junk'
    astrom_loc="/usr/local/bin/"
else:
    print "WHOAMI?"
    sys.exit(1)

# check for w_dir
if os.path.exists(w_dir)==False:
    print "I'm dying... (no w_dir)"
    sys.exit(1)

# get command line args
def argParse():
    parser=ap.ArgumentParser(description="A script to redo the failed minisurvey publishing step")
    parser.add_argument('--astrometry', help = "try redoing the astrometry?", action='store_true')
    parser.add_argument('--manual', help = "manually analyse the images with DS9/DSS", action='store_true')
    parser.add_argument('--yes2all', help = "select this to skip prompting - used if pass already has been made through the imagaes and all are good", action='store_true')
    args=parser.parse_args()
    return args

# read in astrometry.net log files
def getAstromFromFile(astromfile):
    f = open(astromfile, "r").readlines()
    ra=None
    dec=None
    for i in f:
        if i.startswith("Field center: (RA H:M:S"):
            tmp = i.split('=')
            ra,dec = tmp[1].split(',')
            ra = ra.strip()
            ra = ra.replace('(','')
            dec = dec.strip()
            dec = dec.replace(').','')
            break
    return ra, dec

# do the astrometry
def astrometry(image,scale_l,scale_h,ra=None,dec=None,radius=5.0,cpulimit=90):
    astromfile="astrometry_%s.log" % (image)
    command = "%s/solve-field %s --scale-low %s --scale-high %s --cpulimit %s --no-plots --overwrite" % (astrom_loc,image, scale_l, scale_h, cpulimit)
    command = "%s > %s" % (command,astromfile)
    os.system(command)
    ra,dec=getAstromFromFile(astromfile)                            
    return ra,dec

args=argParse()
t=sorted(g.glob('*.fits'))

if args.astrometry:
    RA,DEC=[],[]
    for i in t:
        ra,dec=astrometry(i,2.83,2.93,cpulimit=2)
        if ra:
            RA.append(ra)
            DEC.append(dec)
        else:
            RA.append("0")
            DEC.append("0")

if args.manual: 
    fields=defaultdict(list)
    done=defaultdict(list)
    # loop over the and check for multiples
    # of the same field, if so work on the last one only
    for i in t:
        h=fits.open(i)[0].header['FIELD']
        fields[h].append(i)

    d=ds9()
    time.sleep(5)
    d.set('scale zscale')
    d.set('preserve scale')
    d.set('preserve pan')

    print "Remeber to DELETE duplicate images"
    rm_string=""
    for i in fields:
        d.set('frame clear all')
        image=fields[i][-1]
        h=fits.open(image)[0]
        ra=h.header['CMD_RA']
        dec=h.header['CMD_DEC']

        # print this so we can see which have duplicates to delete
        print fields[i]
        if len(fields[i])>1:
            for k in range(0,len(fields[i])-1):
                rm_string=rm_string+"%s " % (fields[i][k])

        # display the image in DS9 and load the correct region of sky beside it
        d.set('tile yes')
        d.set('frame 1')
        d.set('file %s' % (image))
        d.set('zoom 2')
        d.set('wcs align yes')
        d.set('cmap invert yes')
        
        d.set('frame 2')
        d.set('dsseso coord %.6f %.6f degrees size 30 30 arcmin' % (ra,dec))
        d.set('zoom to fit')
        d.set('wcs align yes')
        d.set('cmap invert yes')
        d.set('frame center all')
        
        if args.yes2all:
            done[i].append(image)
        else:
            yn=raw_input("Do the fields match? (y/n): ")
            if yn.lower().startswith('y'):
                done[i].append(image)
            else:
                continue
    print rm_string

    # need to make an astrometry* log file for the manually solved images?
    # and also a png too, then update the database as with the others, manually?
    table_update_string=""
    if len(done)> 0:
        from create_movie import create_movie
        print "Check the UPDATE strings as use them to UPDATE the minisurvey table"
        for i in done:
            create_movie(done[i],images_directory="%s/" % (w_dir),no_time_series=True,include_increment=False,clobber_images_directory=False,resize_factor=4,multiprocess=False)
            table_update_string=table_update_string+"UPDATE mini_survey SET checked_out=0,astrometry=1,done=1,png=1,fails=0 where image_id=\"%s\";\n" % (done[i][0][5:-5]) # image name minus IMAGE and .fits       

        print table_update_string

