#!/usr/local/python/bin/python
###############################################################################
#                                                                             #
#            Script to make a movie from the previous night's images          #
#                                    v1.2                                     #
#                               James McCormac                                #
#                                                                             #
# Version History:                                                            #
#	20150319	v1.0	Code written                                          #
#   20150321	v1.1	Added montaging + logger                              #
#   20150321	v1.2	Added spltting of png making                          #
#   20150424	v1.3	Added ngwhereis and timer                             #
#                                                                             #
###############################################################################
#
# process:
#	1. get a list of actions from the previous night
#	2. use Simon's create_movie code to generate the pngs
#		splitting the work 3 cams per aux node
#	3. use imagemagick to montage the pngs (getCameraMovie.py snippet)
#	4. use ffmpeg to make the movie of the montaged pngs
#		steps 3+4 happen on one aux node
#
# to do: 
#	factor in 813
#	install bz2 at paranal
#	add checks for failed movie yesterday
#	add uploading of movie to youtube
#	log video ID to database for webpage displaying of embedded video
#

import os, os.path, datetime, sys, time, logging
from datetime import timedelta
from datetime import datetime 
import pymysql 
import logging
import glob as g
from create_movie import create_movie, generate_movie
import numpy as np
import getpass
import argparse as ap

me=getpass.getuser()

######################################################
###################### Globals #######################
######################################################

movie_dir="/ngts/staging/archive/movie/"
top_dir="/ngts/"
logfile="/ngts/staging/archive/logs/movie/"
logging.basicConfig(filename=logfile,level=logging.DEBUG, format='%(levelname)10s - %(message)s')

# empty dictionary for the actions for each camera
cams={801:[],
	802:[],
	803:[],
	804:[],
	805:[],
	806:[],
	807:[],
	808:[],
	809:[],
	810:[],
	811:[],
	812:[],
	899:[]}

# set the key to the das machines for each camera
das={801:None,
	802:None,
	803:None,
	804:None,
	805:None,
	806:None,
	807:None,
	808:None,
	809:None,
	810:None,
	811:None,
	812:None}

# start id for movie
start_id={801:-1,
	802:-1,
	803:-1,
	804:-1,
	805:-1,
	806:-1,
	807:-1,
	808:-1,
	809:-1,
	810:-1,
	811:-1,
	812:-1,
	899:-1}

######################################################
##################### Functions ######################
######################################################

def ArgParse():
	parser=ap.ArgumentParser()
	parser.add_argument("--pngs",help="make the PNG files")
	parser.add_argument("--montage",help="montage all PNG files",action="store_true")
	parser.add_argument("--movie",help="make movie from montaged PNG files",action="store_true")
	parser.add_argument("--tidy",help="tidy up pngs?",action="store_true")
	args=parser.parse_args()
	return args

def getDasLoc():
	'''
	Find the camera/das locations
	'''
	for i in das:
		if i != 899:
			s=os.popen('/usr/local/paladin/bin/ngwhereis %d' % (i)).readline()
			try:
				das[i]=s.split()[0]
			except IndexError:
				das[i]=None
			print s

def getLastNight():
	'''
	Get the night int for last night
	'''
	tnow=datetime.utcnow()
	if tnow.hour < 15:
		delta=-1
	else:
		delta=0
	return int((tnow+delta*timedelta(days=1)).strftime('%Y%m%d'))

def make_pngs(clist):
	'''
	Get all the images from yesterday and make pngs 
	for the daily montage. PNGs will be stored in 
	
	/ngts/staging/archive/movie/dasXX/ 
	
	These will be removed each day once the movie is made
	'''
	db=pymysql.connect(host='ds',db='ngts_ops')
	qry="SELECT action_id,camera_id,action FROM action_list WHERE night=%d" % (getLastNight())
	with db.cursor() as cur:
		cur.execute(qry)
		for row in cur:
			if row[2] != 'stow':
				cams[row[1]].append("action%s_%s" % (row[0],row[2]))
	del cams[899]
	for i in cams:
		if str(i) in clist:
			if len(cams[i]) > 0 and das[i] != None:
				if os.path.exists(movie_dir) == False:
					os.mkdir(movie_dir)	
				logger.info(movie_dir)
				for j in cams[i]:
					logger.info("%s - %s%s/%s/*.fits" % (datetime.utcnow().isoformat(),top_dir,das[i],j))
					t=sorted(g.glob('%s%s/%s/*.fits' % (top_dir,das[i],j)))
					camera_movie_dir=movie_dir+das[i]
					create_movie(t,images_directory=camera_movie_dir,include_increment=False,
						clobber_images_directory=False,resize_factor=4)
			else:
				logger.warn('No images for %d' % (i))
		else:
			continue
	db.close()

def getDatetime(t):
	'''
	get the date and time from a raw image filename
	and create a datetime variable
	'''
	ychk=int(t[8:12])
	mthchk=int(t[12:14])
	dchk=int(t[14:16])
	hchk=int(t[16:18])
	minchk=int(t[18:20])
	schk=int(t[20:22])
	x=datetime.datetime(year=ychk,month=mthchk,
		day=dchk,hour=hchk,minute=minchk,second=schk)
	return x
	

def make_montage(movie_dir,das):
	'''
	sync the pngs according to earliest image that day then
	montage all the pngs with imagemagick
	'''
	if os.path.exists(movie_dir) == False:
		os.mkdir(movie_dir)
	os.chdir(movie_dir)		
	logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
	
	t_refs=[]
	das_tracker=[]
	imlens=[]
	
	##############################
	# scan all folders looking for 
	# earliest image of the night
	##############################
	noimages=0
	for i in das:
		if das[i] != None:
			os.chdir(das[i])
			logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
			t=sorted(g.glob('*.png'))
			if len(t) == 0:
				os.chdir('../')
				logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
				continue
			x=getDatetime(t[0])				
			t_refs.append(x)
			imlens.append(len(t))
			das_tracker.append(das[i])
			noimages+=1
			os.chdir('../')
			logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
	
	# check for no data exit if so
	if noimages == 0:
		logger.fatal("%s - No pngs found, exiting..." % (datetime.utcnow().isoformat()))
		sys.exit(1)
	
	# list of earliest times per camera
	# and length of imaging run		
	t_refs=np.array(t_refs)		
	imlens=np.array(imlens)
	
	# now work out which was the earliest and go there to start the time series
	n=np.where(t_refs==min(t_refs))[0]
	if len(n) > 1:
		n=n[0]
	logger.info("%s - Reference DAS machine: %s" % (datetime.utcnow().isoformat(),das_tracker[n]))

	##############################
	# start in earliest folder and
	# generate a list of reference times
	##############################	
	
	os.chdir(das_tracker[n])
	logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))

	# these are the time slots, match the other images to start with a certain slot
	slots=np.arange(0,imlens[n],1)
	
	# reset t_refs for start_id calculations
	t=sorted(g.glob('*.png'))
	t_refs=[]
	for i in range(0,len(t)):		
		x=getDatetime(t[i])
		t_refs.append(x)
	
	os.chdir('../')
	logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
	
	
	##############################
	# now go through each other dir and
	# generate their starting points
	##############################
	
	for i in das:
		if das[i] != None:
			os.chdir(das[i])
			logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
			
			t=sorted(g.glob('*.png'))
			if len(t) == 0:
				os.chdir('../')
				logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
				continue
				
			x=getDatetime(t[0])	
			diff=[]
			for j in range(0,len(t_refs)):
				diff.append(abs((t_refs[j]-x).total_seconds()))
			
			z=diff.index(min(diff))
			start_id[i]=z
			
			os.chdir('../')
			logger.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
	
	logger.info("%s - Dictionary of start_ids:" % (datetime.utcnow().isoformat()))
	logger.info(start_id)
	
	##############################
	# work out the new video size for
	# non time overlapping images
	##############################
	 
	max_start=0
	for i in start_id:
		if start_id[i]>max_start:
			max_start=start_id[i]
	run_len=int(max(imlens)+max_start)
	
	##############################
	# montage based on start_ids
	##############################
	
	# keep a dictionary of the directory contents from 
	# first glob as to not check each time we loop around...
	t={801:[],
		802:[],
		803:[],
		804:[],
		805:[],
		806:[],
		807:[],
		808:[],
		809:[],
		810:[],
		811:[],
		812:[]}
	
	for i in range(0,run_len):
		files=""
		for j in das:
			if i==0:
				if das[j] != None:
					t[j].append(sorted(g.glob('%s/*.png' % (das[j]))))
				else:
					t[j].append([])
			
			if start_id[j] == -1 or i < start_id[j]:
				files=files+"empty/empty.png "
			else:
				try:
					files=files+t[j][0][i-start_id[j]]+" " 
				except IndexError:
					files=files+"empty/empty.png "
					
		logger.debug("%s - [%d/%d] %s" % (datetime.utcnow().isoformat(),i+1,run_len,files))
		
		# now montage them together
		comm="/usr/local/bin/montage %s -tile 6x2 -geometry 400x300-80+3 tiled_%05d.png" % (files,i)
		logger.debug("%s - %s" % (datetime.utcnow().isoformat(),comm))
		os.system(comm)


def make_movie(movie_dir,movie):
	generate_movie(movie_dir,movie)
	

def main():	
	args=ArgParse()
	getDasLoc()
		
	# check all machines are up
	cont=0
	for i in das:
		if das[i]:
			x=os.popen('ping -w 0.2 -c 1 %s' % (das[i])).readlines()
			if ' 0% packet loss' in x[-2]:
				cont+=0
			else:
				cont+=1			
	if cont > 0:
		logger.fatal("%s - MACHINES ARE DOWN - ignoring image generation (NFS issues?)" % (datetime.utcnow().isoformat()))
		sys.exit(1)
	
	# get time of start
	t1=datetime.datetime.utcnow()
			
	if args.pngs:
		# remove any images from yesterday	
		for i in das:
			if das[i] != None:
				os.system('/bin/rm %s/%s/IMAGE*.png' % (movie_dir,das[i]))
		ex=0
		# check the camera list
		csplit=args.pngs.split(',')
		if len(csplit) < 1:
			ex+=1
		else:
			for i in csplit:
				if int(i) not in cams:
					ex+=1			
		if ex > 0:
			logger.fatal("%s - Problem in pngs..." % (datetime.utcnow().isoformat()))
			logger.fatal("%s - Enter list like --pngs 801,802,803,...8[n]" % (datetime.utcnow().isoformat()))
			logger.fatal("%s - Exiting..." % (datetime.utcnow().isoformat()))
			sys.exit(1)
		else:
			make_pngs(args.pngs)	
	if args.montage:
		make_montage(movie_dir,das)
	if args.movie:
		movie_date=(datetime.datetime.utcnow()-timedelta(days=1)).strftime('%Y%m%d')
		movie_name="%s/daily_movies/movie_%s.mp4" % (movie_dir,movie_date)
		make_movie(movie_dir,movie_name)		
		# clean up the pngs
		if args.tidy:
			os.system('/bin/rm %s/tiled*.png' % (movie_dir))
		for i in das:
			if das[i] != None and args.tidy:
				os.system('/bin/rm %s/%s/IMAGE*.png' % (movie_dir,das[i]))
		
	t2=datetime.datetime.utcnow()
	dt=(t2-t1).total_seconds()/60.
	
	print "Runtime: %.2f mins" % (dt) 
	
if __name__=='__main__':
	main()			
	
