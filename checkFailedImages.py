#!/usr/local/python/bin/python
# script to check the previously unsolved files
import os
import glob as g

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

RA,DEC=[],[]

t=sorted(g.glob('*.fits'))
for i in t:
	ra,dec=astrometry(i,2.83,2.93,cpulimit=2)
	if ra:
		RA.append(ra)
		DEC.append(dec)
	else:
		RA.append("0")
		DEC.append("0")