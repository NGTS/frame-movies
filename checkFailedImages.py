#!/usr/local/python/bin/python
# script to check the previously unsolved files
import os
import glob as g

w_dir="/ngts/staging/archive/minisurvey"
astrom_loc="/usr/local/astrometry.net/bin/"

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

def astrometry(image,scale_l,scale_h,ra=None,dec=None,radius=5.0,cpulimit=90):
	astromfile="astrometry_%s.log" % (image)
	command = "%s/solve-field %s --scale-low %s --scale-high %s --cpulimit %s --no-plots --overwrite" % (astrom_loc,image, scale_l, scale_h, cpulimit)
	command = "%s > %s" % (command,astromfile)
	os.system(command)
	ra,dec=getAstromFromFile(astromfile)							
	return ra,dec


t=sorted(g.glob('*.fits'))

redo_astrometry = 0
analyse_manually = 1

if redo_astrometry>0:
	RA,DEC=[],[]
	for i in t:
		ra,dec=astrometry(i,2.83,2.93,cpulimit=2)
		if ra:
			RA.append(ra)
			DEC.append(dec)
		else:
			RA.append("0")
			DEC.append("0")

if analyse_manually > 0:
	from astropy.io import fits
	from collections import defaultdict
	from ds9 import *
	import time
	
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

	for i in fields:
		d.set('frame clear all')
		image=fields[i][-1]
		h=fits.open(image)[0]
		ra=h.header['CMD_RA']
		dec=h.header['CMD_DEC']

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
		yn=raw_input("Do the fields match? (y/n): ")
		if yn.lower().startswith('y'):
				done[i].append(image)
		else:
			continue

	# need to make an astrometry* log file for the manually solved images?
	# and also a png too, then update the database as with the others, manually?
	if len(done)> 0:
		from create_movie import create_movie
		w_dir="/Users/James/Desktop/minisurvey/junk"

		for i in done:
			create_movie(done[i],images_directory="%s/" % (w_dir),no_time_series=True,include_increment=False,clobber_images_directory=False,resize_factor=4,multiprocess=False)

