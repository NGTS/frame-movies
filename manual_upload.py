
import os,pymysql
import sys

if len(sys.argv) < 2:
    print('USAGE: python manual_upload.py YYYYMMD')
    sys.exit(1)

night=int(sys.argv[1])
video_summary_file="/ngts/staging/archive/movie/daily_movies/daily_movies.html"
movie_dir="/ngts/staging/archive/movie/"
movie_name="%s/daily_movies/movie_%d.mp4" % (movie_dir,night)

def upload2youtube(filename,title):
  '''
  Upload the movie to YouTube using the OAuth setup for NGTS-OPS user channel
  '''
  #logging.info("%s - Uploading video to YouTube" % (datetime.utcnow().isoformat()))
  v_id=os.popen("/usr/local/python/bin/python /usr/local/cron/scripts/upload2youtube.py --file=%s --title=%s --description='NGTS Daily Movie' --category='22' --privacyStatus='unlisted'"% (filename,title)).readlines()
  video_id=v_id[1].split()[2].replace("'","")
  #logging.info("%s - Video ID: %s" % (datetime.utcnow().isoformat(),video_id))
  return video_id



def logVideoId(video_id,night):
  db=pymysql.connect(host='ds',db='ngts_ops')
  qry="INSERT INTO daily_movies (night,youtube_id) VALUES (%d,'%s')" % (night,video_id)
  #logging.info("%s - Logging video ID" % (datetime.utcnow().isoformat()))
  #logging.info("%s - %s" % (datetime.utcnow().isoformat(),qry))
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
  #logging.info("%s - Making video summary table" % (datetime.utcnow().isoformat()))
  #logging.info("%s - %s" % (datetime.utcnow().isoformat(),qry))
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


video_id=upload2youtube(movie_name,night)
logVideoId(video_id,night)
makeSummaryTable(video_summary_file)
