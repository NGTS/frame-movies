#!/usr/local/python/bin/python
###############################################################################
#                                                                             #
#            Script to make a movie from the previous night's images          #
#                                    v1.4                                     #
#                               James McCormac                                #
#                                                                             #
# Version History:                                                            #
#   20150319    v1.0    Code written                                          #
#   20150321    v1.1    Added montaging + logging                             #
#   20150321    v1.2    Added spltting of png making                          #
#   20150424    v1.3    Added ngwhereis and timer                             #
#   20151230    v1.4    Added movie logging, youtube uploading and summary    #
#                                                                             #
###############################################################################
#
# process:
#   1. get a list of actions from the previous night
#   2. use Simon's create_movie code to generate the pngs
#       splitting the work 3 cams per aux node
#   3. use imagemagick to montage the pngs (getCameraMovie.py snippet)
#   4. use ffmpeg to make the movie of the montaged pngs
#       steps 3+4 happen on one aux nod
#   5. upload the movie to youtube for embedding on monitor page
#   6. log the youtube video id to the database 
#   7. create static summary table for subsequent js rowhandler to 
#       load the videos when clicked upon
#
# to do: 
#   factor in 813
#   add movie making status to web page
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
video_summary_file="/ngts/staging/archive/movie/daily_movies/daily_movies.html"
logging.basicConfig(filename=logfile,level=logging.DEBUG, format='%(levelname)10s - %(message)s')

# empty dictionary for the actions for each camera
cams={801:[],
    802:[],
    803:[],
    804:[],
    806:[],
    807:[],
    808:[],
    809:[],
    810:[],
    811:[],
    812:[],
    813:[],
    899:[]}

# set the key to the das machines for each camera
das={801:None,
    802:None,
    803:None,
    804:None,
    806:None,
    807:None,
    808:None,
    809:None,
    810:None,
    811:None,
    812:None,
    813:None}

# start id for movie
start_id={801:-1,
    802:-1,
    803:-1,
    804:-1,
    806:-1,
    807:-1,
    808:-1,
    809:-1,
    810:-1,
    811:-1,
    812:-1,
    813:-1,
    899:-1}

######################################################
##################### Functions ######################
######################################################

def argParse():
    parser=ap.ArgumentParser()
    parser.add_argument("--pngs",help="make the PNG files")
    parser.add_argument("--montage",help="montage all PNG files",action="store_true")
    parser.add_argument("--movie",help="make movie from montaged PNG files",action="store_true")
    parser.add_argument("--tidy",help="tidy up pngs?",action="store_true")
    parser.add_argument("--upload",help="upload movie to YouTube",action="store_true")
    args=parser.parse_args()
    return args

def getDasLoc():
    '''
    Find the camera/das locations
    '''
    logging.info("%s - Finding camera locations" % (datetime.utcnow().isoformat()))
    for i in das:
        if i != 899:
            s=os.popen('/usr/local/paladin/bin/ngwhereis %d' % (i)).readline()
            try:
                das[i]=s.split()[0]
            except IndexError:
                das[i]=None
            logging.info("%s - %s" % (datetime.utcnow().isoformat(),s))

def getLastNight():
    '''
    Get the night int for last night
    '''
    tnow=datetime.utcnow()
    if tnow.hour < 18:
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
    logging.info("%s - Making pngs" % (datetime.utcnow().isoformat()))
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
                logging.info(movie_dir)
                for j in cams[i]:
                    logging.info("%s - %s%s/%s/*.fits" % (datetime.utcnow().isoformat(),top_dir,das[i],j))
                    t=sorted(g.glob('%s%s/%s/*.fits' % (top_dir,das[i],j)))
                    camera_movie_dir=movie_dir+das[i]
                    create_movie(t,images_directory=camera_movie_dir,include_increment=False,
                        clobber_images_directory=False,resize_factor=4)
            else:
                logging.warn('No images for %d' % (i))
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
    x=datetime(year=ychk,month=mthchk,
        day=dchk,hour=hchk,minute=minchk,second=schk)
    return x
    

def make_montage(movie_dir,das):
    '''
    sync the pngs according to earliest image that day then
    montage all the pngs with imagemagick
    '''
    logging.info("%s - Making montage" % (datetime.utcnow().isoformat()))
    if os.path.exists(movie_dir) == False:
        os.mkdir(movie_dir)
    os.chdir(movie_dir)     
    logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
    
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
            logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
            t=sorted(g.glob('*.png'))
            if len(t) == 0:
                os.chdir('../')
                logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
                continue
            x=getDatetime(t[0])             
            t_refs.append(x)
            imlens.append(len(t))
            das_tracker.append(das[i])
            noimages+=1
            os.chdir('../')
            logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
    
    # check for no data exit if so
    if noimages == 0:
        logging.fatal("%s - No pngs found, exiting..." % (datetime.utcnow().isoformat()))
        sys.exit(1)
    
    # list of earliest times per camera
    # and length of imaging run     
    t_refs=np.array(t_refs)     
    imlens=np.array(imlens)
    
    # now work out which was the earliest and go there to start the time series
    n=np.where(t_refs==min(t_refs))[0]
    if len(n) > 1:
        n=n[0]
    logging.info("%s - Reference DAS machine: %s" % (datetime.utcnow().isoformat(),das_tracker[n]))

    ##############################
    # start in earliest folder and
    # generate a list of reference times
    ##############################  
    
    os.chdir(das_tracker[n])
    logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))

    # these are the time slots, match the other images to start with a certain slot
    slots=np.arange(0,imlens[n],1)
    
    # reset t_refs for start_id calculations
    t=sorted(g.glob('*.png'))
    t_refs=[]
    for i in range(0,len(t)):       
        x=getDatetime(t[i])
        t_refs.append(x)
    
    os.chdir('../')
    logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
    
    
    ##############################
    # now go through each other dir and
    # generate their starting points
    ##############################
    
    for i in das:
        if das[i] != None:
            os.chdir(das[i])
            logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
            
            t=sorted(g.glob('*.png'))
            if len(t) == 0:
                os.chdir('../')
                logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
                continue
                
            x=getDatetime(t[0]) 
            diff=[]
            for j in range(0,len(t_refs)):
                diff.append(abs((t_refs[j]-x).total_seconds()))
            
            z=diff.index(min(diff))
            start_id[i]=z
            
            os.chdir('../')
            logging.info("%s - Moving to: %s" % (datetime.utcnow().isoformat(),os.getcwd()))
    
    logging.info("%s - Dictionary of start_ids:" % (datetime.utcnow().isoformat()))
    logging.info(start_id)
    
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
        806:[],
        807:[],
        808:[],
        809:[],
        810:[],
        811:[],
        812:[],
        813:[]}
    
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
                    
        logging.info("%s - [%d/%d] %s" % (datetime.utcnow().isoformat(),i+1,run_len,files))
        
        # now montage them together
        comm="/usr/local/bin/montage %s -tile 6x2 -geometry 400x300-80+3 tiled_%05d.png" % (files,i)
        logging.info("%s - %s" % (datetime.utcnow().isoformat(),comm))
        os.system(comm)


def make_movie(movie_dir,movie):
    '''
    Make a movie of the montaged images
    '''
    t=g.glob('%s/tiled*.png' % (movie_dir))
    if len(t)>0:
        logging.info("%s - Making movie" % (datetime.utcnow().isoformat()))
        generate_movie(movie_dir,movie)
    else:
        logging.info("%s - No tiled images, skipping" % (datetime.utcnow().isoformat()))
        sys.exit(1)
        
def upload2youtube(filename,title):
    '''
    Upload the movie to YouTube using the OAuth setup for NGTS-OPS user channel
    '''
    logging.info("%s - Uploading video to YouTube" % (datetime.utcnow().isoformat()))
    v_id=os.popen("/usr/local/python/bin/python /usr/local/cron/scripts/upload2youtube.py --file=%s --title=%d --description='NGTS Daily Movie' --category='22' --privacyStatus='unlisted'"% (filename,title)).readlines()
    video_id=v_id[1].split()[2].replace("'","")
    logging.info("%s - Video ID: %s" % (datetime.utcnow().isoformat(),video_id))
    return video_id

def logVideoId(video_id,night):
    db=pymysql.connect(host='ds',db='ngts_ops')
    qry="INSERT INTO daily_movies (night,youtube_id) VALUES (%d,'%s')" % (night,video_id)
    logging.info("%s - Logging video ID" % (datetime.utcnow().isoformat()))
    logging.info("%s - %s" % (datetime.utcnow().isoformat(),qry))
    with db.cursor() as cur:
        cur.execute(qry)
        db.commit()
    db.close()

def Td(text, class_id, width):
    return "<td class=%s width=%d>%s</td>" % (class_id,width,text)

def wrapRow(elements):
    return "<tr>%s</tr>\n" % (elements)

def makeSummaryTable(htmlname):
    db=pymysql.connect(host='ds',db='ngts_ops')
    qry="SELECT night,youtube_id FROM daily_movies ORDER BY night DESC"
    night,youtube_id=[],[]
    logging.info("%s - Making video summary table" % (datetime.utcnow().isoformat()))
    logging.info("%s - %s" % (datetime.utcnow().isoformat(),qry))
    with db.cursor() as cur:
        cur.execute(qry)
        for row in cur:
            night.append(row[0])
            youtube_id.append(row[1])
    db.close()
    f=open(htmlname,'w')
    outstr="<table class='daily_movies' id='daily_movies'>\n"
    for i in range(0,len(night)):
        line=Td(night[i],"",80)+Td(youtube_id[i],"",80)
        outstr=outstr+wrapRow(line)
    outstr=outstr+"</table>"    
    f.write(outstr)
    f.close()


def pingDas(das):
    c = 0
    while c < 10:
        logging.info('%s - pinging %s - attempt %d' % (datetime.utcnow().isoformat(), das, c+1))
        x=os.popen('ping -w 0.2 -c 1 %s' % (das)).readlines()
        if '0% packet loss' in x[-2]:
            return 0
        c += 1
    return 1

def main(): 
    args=argParse()
    getDasLoc()
    night=getLastNight()
    movie_name="%s/daily_movies/movie_%d.mp4" % (movie_dir,night)   
    
    # get time of start
    t1=datetime.utcnow()
    # check all machines are up
    cont=0
    for i in das:
        if das[i]:
            cont += pingDas(das[i])
    if cont > 0:
        logging.fatal("%s - MACHINES ARE DOWN - ignoring image generation (NFS issues?)" % (datetime.utcnow().isoformat()))
        sys.exit(1)     
    if args.pngs:
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
            logging.fatal("%s - Problem in pngs..." % (datetime.utcnow().isoformat()))
            logging.fatal("%s - Enter list like --pngs 801,802,803,...8[n]" % (datetime.utcnow().isoformat()))
            logging.fatal("%s - Exiting..." % (datetime.utcnow().isoformat()))
            sys.exit(1)
        else:
            make_pngs(args.pngs)    
    if args.montage:
        make_montage(movie_dir,das)
    if args.movie:
        make_movie(movie_dir,movie_name)        
        # clean up the pngs
        if args.tidy and os.path.exists(movie_name):
            logging.info("%s - Removing tiled pngs" % (datetime.utcnow().isoformat()))
            os.system('/bin/rm %s/tiled*.png' % (movie_dir))
        if os.path.exists(movie_name) == False:
            logging.fatal("%s - NO MOVIE FILE! QUITTING" % (datetime.utcnow().isoformat()))
            sys.exit(1)
        for i in das:
            if das[i] != None and args.tidy and os.path.exists(movie_name):
                logging.info("%s - Removing individual pngs" % (datetime.utcnow().isoformat()))
                os.system('/bin/rm %s/%s/IMAGE*.png' % (movie_dir,das[i]))
    if args.upload and os.path.exists(movie_name):
        if os.path.exists(movie_name):
            video_id=upload2youtube(movie_name,night)
            logVideoId(video_id,night)
            makeSummaryTable(video_summary_file)
        else:
            logging.fatal("%s - No such movie file: %s" % (datetime.utcnow().isoformat(),movie_name))

    t2=datetime.utcnow()
    dt=(t2-t1).total_seconds()/60.  
    logging.info("%s - Runtime: %.2f mins" % (datetime.utcnow().isoformat(),dt))
    
if __name__=='__main__':
    main()          
    
