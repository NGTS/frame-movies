# script to publish the mini survey data
# check the astrometry and make pngs for the webpages

import os, sys, time, logging, getpass, pymysql
import argparse as ap
from datetime import datetime as dt
from datetime import timedelta
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
import numpy as np
from create_movie import create_movie

# whoami?
me=getpass.getuser()

# connect to database
if me == "James":
	db=pymysql.connect(host='localhost',db='ngts_prep')
	logfile="/Users/James/Desktop/www_cron/ngminisurvey.log"
	w_dir="/Users/James/Desktop/www_cron/minisurvey"
	astrom_loc="/usr/local/bin/"
elif me=="ops":
	db=pymysql.connect(host='ds',db='ngts_ops')
	logfile="/usr/local/cron/logs/ngminisurvey.log"
	w_dir="/usr/local/cron/work/minisurvey"
	astrom_loc="/usr/local/astrometry.net/bin/"
else:
	print "WHOAMI!?"
	sys.exit(1)

# logging set up
logging.basicConfig(filename=logfile,level=logging.DEBUG, format='%(levelname)10s - %(message)s')

# function to parse the command line
def argParse():
	parser=ap.ArgumentParser()
	parser.add_argument('--debug',help='run in debugging mode',action='store_true')
	return parser.parse_args()

args=argParse()

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

# do the astrometry with astrometry.net
def astrometry(image,scale_l,scale_h,ra=None,dec=None,radius=5.0,cpulimit=90):
	astromfile="astrometry_%s.log" % (image)
	if os.path.exists(astromfile) == False:
		if ra and dec:
			command = "%s/solve-field %s --ra %s -- dec %s --radius %s --scale-low %s --scale-high %s --cpulimit %s --no-plots --overwrite" % (astrom_loc,image, ra, dec, radius, scale_l, scale_h, cpulimit)
		else:
			command = "%s/solve-field %s --scale-low %s --scale-high %s --cpulimit %s --no-plots --overwrite" % (astrom_loc,image, scale_l, scale_h, cpulimit)
		
		command = "%s > %s" % (command,astromfile)
		os.system(command)
	
	ra,dec=getAstromFromFile(astromfile)							
	return ra,dec

# function to check the astrometry and update the database
# and/or return fields to the pile for another attempt
def checkAstrometry():
	qry="SELECT action_id,image_id,camera_id FROM mini_survey WHERE done=1 AND astrometry=0"
	logging.info('%s %s' % (dt.utcnow().isoformat(),qry))
	cur=db.cursor()
	cur.execute(qry)

	action_id_a,image_id_a,camera_id_a=[],[],[]
	for row in cur:
		action_id_a.append(row[0])
		image_id_a.append(row[1])
		camera_id_a.append(row[2])
		das=os.popen('ngwhereis %s' % (row[2])).readlines()[0].split()[0]
		cp_comm='cp /ngts/%s/action%s_observeField/IMAGE%s* %s/' % (das,row[0],row[1],w_dir)
		os.system(cp_comm)
		logging.info('%s %s' % (dt.utcnow().isoformat(),cp_comm))
		
	here=os.getcwd()
	os.chdir(w_dir)
	logging.info('%s Moving to %s' % (dt.utcnow().isoformat(),w_dir))
	if os.path.exists('junk')==False:
		os.mkdir('junk')
	
	fails=[]
	for i in image_id:
		# unzip if compressed
		zipfile='IMAGE%s.fits.bz2' % (i)
		if os.path.exists(zipfile):
			logging.info('%s UNZIPPING %s' % (dt.utcnow().isoformat(),zipfile))
			os.system('bunzip2 %s' % (zipfile))
		
		# get the commanded position
		imfile='IMAGE%s.fits' % (i)
		hdr=fits.open(imfile)[0].header
		rin=hdr['CMD_RA']
		din=hdr['CMD_DEC']
		c=SkyCoord(ra=rin,dec=din,unit=(u.deg,u.deg),frame='icrs')
		
		# do astrometry for actual positon
		ra_a,dec_a=astrometry(imfile,2.83,2.93,cpulimit=2)
		
		# check output
		if ra_a == None or dec_a == None:
			logging.error('%s COULD NOT DO ASTROMETRY FOR %s' % (dt.utcnow().isoformat(),imfile))
			qry="UPDATE mini_survey SET done=0, fails=ISNULL(fails,0)+1 WHERE image_id='%s'" % (i)
			logging.info("%s REMOVING %s FROM %s " % (dt.utcnow().isoformat(),imfile,w_dir))
			os.system('mv *%s* junk/' % (i))
		else:			
			a=SkyCoord(ra=ra_a, dec=dec_a, unit=(u.hourangle, u.deg), frame='icrs')
			sep_ang=c.separation(a).arcmin
			if sep_ang>10:
				logging.error("%s IMAGE IS OFF BY >10 ARCMIN (%.2f), REPEAT FIELD" % (dt.utcnow().isoformat(),sep_ang))
				qry="UPDATE mini_survey SET done=0, fails=ISNULL(fails,0)+1 WHERE image_id='%s'" % (i)
				logging.info("%s REMOVING %s FROM %s " % (dt.utcnow().isoformat(),imfile,w_dir))
				os.system('mv *%s* junk/' % (i))
			else:
				logging.info("%s IMAGE%s.fits solved with error of %.2f arcmin" % (dt.utcnow().isoformat(),i,sep_ang))
				qry="UPDATE mini_survey SET astrometry=1 WHERE image_id='%s'" % (i)
			
			if not args.debug:
				cur.execute(qry)
				db.commit()
			
	os.chdir(here)
	logging.info('%s Returning to %s' % (dt.utcnow().isoformat(),here))	

def makePNGs():
	here=os.getcwd()
	os.chdir(wdir)
	logging.info('%s Moving to %s' % (dt.utcnow().isoformat(),w_dir))	
	
	qry="SELECT action_id,image_id,camera_id FROM mini_survey WHERE done=1 AND astrometry=1 AND png=0"
	logging.info('%s %s' % (dt.utcnow().isoformat(),qry))
	cur=db.cursor()
	cur2=db.cursor()
	cur.execute(qry)
	
	action_id_a,image_id_a,camera_id_a=[],[],[]
	for row in cur:
		action_id_a.append(row[0])
		image_id_a.append(row[1])
		camera_id_a.append(row[2])
		das=os.popen('ngwhereis %s' % (row[2])).readlines()[0].split()[0]	
		imfile="IMAGE%s.fits" % (image_id)
		if not args.debug:
			create_movie([imfile],images_directory="%s/pngs" % (w_dir),no_time_series=True,include_increment=False,clobber_images_directory=False,resize_factor=4)
			logging.info("%s Making PNG of %s" % (dt.utcnow().isoformat(),imfile))
			
		qry2="UPDATE mini_survey SET png=1 WHERE image_id=%d" % (row[1])
		logging.info("%s %s") % (dt.utcnow().isoformat(),qry2))
		if not args.debug:
			cur2.execute(qry2)
			db.commit()
		
	os.chdir(here)
	logging.info('%s Returning to %s' % (dt.utcnow().isoformat(),here))	
	
def main():
	checkAstrometry()
	makePNGs()
	

if __name__=="__main__":
	main()
	
