#
# This utility runs segmentation / encoding process
# and registers new chunks on the server
# and takes the following arguments
#  segmenterBinary mcastAddr:port /temp/storage/dir /encrypted/storage/dir 
#

# EXTRA OPTIONS which are directly passed to FFMPEG
# are defined at http://ffmpeg.org/ffmpeg.html#udp

#
# CONFIGURATION is imported form settings.py
#
from settings import *

import datetime
import binascii
import subprocess
from subprocess import PIPE
import logging 
import os, re, sys
import urllib, urllib2

# segmenter: tstamp=1318975595.280000, sequence=98, duration=10.200000, end=0, file=/work/sgm/run2/ts-00098.ts
SEGMENTER_OUTPUT_PATTERN = re.compile("segmenter:\s*tstamp=(?P<startTimeEpoch>[0-9\.]+),\s*sequence=(?P<sequence>[0-9]+),\s*duration=(?P<duration>[0-9\.]+),\s*end=(?P<done>[0-9]),\s*file=(?P<file>\S+)$")

UDP_ADDR_PATTERN = re.compile("^udp://(?P<host>[0-9\.]+):(?P<port>[0-9]+)\S*$")

def mkdir_or_die(path):
	if os.path.isdir(path):
		return path

	try :
		os.makedirs(path)
		return path
	except os.OSError, e:
		sys.stderr.write('Failed to create %s : %s\n' % (path, e))
		sys.exit(-1);

def genKey():
	return binascii.hexlify(subprocess.Popen(['openssl', 'rand', '16'], stdin=None, stderr=None, stdout=PIPE).communicate()[0])

def process(channelID, addrUrl, delaySeconds):
	
	addrMatch = UDP_ADDR_PATTERN.match(addrUrl)
	if not addrMatch:
		sys.stderr.write('%s should be in form udp://xxx.xxx.xxx.xxx:pppp\n'%addrUrl)
		sys.exit(-1)

	mcastAddr = addrMatch.groupdict()

	# CHECK PATHS
	if not os.path.exists(PATH_REPLACE[0]) or not os.path.isdir(PATH_REPLACE[0]):
		sys.stderr.write("the replacement part %s is not a folder\n"%PATH_REPLACE[0])
		return
	
	if ENCRYPTED_DIR.find(PATH_REPLACE[0]) > 0:
		sys.stderr.write("REPLACE_PATH %s should be part of %s\n" % (PATH_REPLACE[0], ENCRYPTED_DIR))
		return
	
	
	tm = datetime.datetime.utcnow()
	if (not ENCRYPT):
		cleanDir= mkdir_or_die("%s/%s/%s"%(CLEAN_DIR, channelID, timePrefix))
	else:
		cleanDir= mkdir_or_die("%s/%s"%(CLEAN_DIR, channelID))

	logDir 	= mkdir_or_die("%s/%s"%(LOG_DIR, channelID))
	timePrefix = "%u%02u%02u_%02u%02uUTC" % (tm.year, tm.month, tm.day, tm.hour, tm.minute)
	encDir	= mkdir_or_die("%s/%s/%s" % (ENCRYPTED_DIR, channelID, timePrefix))

	log = logging.getLogger('segmenter.py')
	hdlr = logging.FileHandler("%s/%s.log" % (logDir, timePrefix))
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
	hdlr.setFormatter(formatter)
	log.addHandler(hdlr)
	log.setLevel(logging.INFO)

	# MAIN LOOP
	log.info("Starting segmentation process channel=%s from %s" % (channelID, mcastAddr))
	log.info("CLEAN     : %s" % cleanDir)
	log.info("ENCRYPTED : %s" % encDir)
 
	filePrefix = 'ts-%s'%channelID
	segmenterProc = subprocess.Popen([SEGMENTER_PATH, addrUrl, '%u'%SEGMENT_DURATION_SECONDS, cleanDir, filePrefix], stdin=None, stdout=None, stderr=PIPE)

	if segmenterProc.poll() != None:
		log.error('segmentation process did not start. abort')
		return
	input = segmenterProc.stderr
	
	keyExpire = 0
	while True:
		# check if we need generate a new AES key
		if keyExpire <= 0:
			key = genKey()
			initVector = genKey()
			keyExpire = KEY_ROTATE_SEGMENTS
		out = input.readline().strip('\n\r')
		if segmenterProc.poll() != None:
			# the segmenter process was terminated
			log.error("segmenter process terminated %s"%out);
			break
		

		param = SEGMENTER_OUTPUT_PATTERN.match(out)
		if param is None:
			# could be debug messages, etc - just skipping
			log.warning(out)
			continue
		else:
			param = param.groupdict()
		
		log.info("Got new chunk %s"%param);
		if (ENCRYPT):
			outPath		= os.path.normpath(encDir+'/' + os.path.split(param['file'])[1])
			# got an output, now encrypt it
			try:
				subprocess.check_call([OPENSSL_PATH, 'aes-128-cbc', '-e', 
					'-in', 	param['file'],
					'-out',	outPath,
					'-nosalt',
					'-K', key,
					'-iv', initVector,
				], stdin=None, stdout=None, stderr=None)
				log.debug('encrypted %s key=%s iv=%s' % (outPath, key, initVector))
				keyExpire -= 1
			except subprocess.CalledProcessError as e:
				log.error(e)
				break
			
			if not KEEP_CLEAN:
				log.info("Removing %s" % param['file'])
				os.remove(param['file'])
		else:
			outPath = param['file']
	
		requestString = API_ADD_CHUNK+'?'+urllib.urlencode({
				'channelID'		 : channelID,
				'appType'		 : '2', # NPVR
				'apiKey'		 : API_KEY,
				'sequence' 		 : param['sequence'],
				'startTimeEpoch' : param['startTimeEpoch'],
				'duration'	 	 : param['duration'],
				'aesKey'		 : key,
				'aesIV' 		 : initVector,
				'bytes'			 : os.path.getsize(outPath),
				'file'			 : outPath.replace(PATH_REPLACE[0], PATH_REPLACE[1])
		})
		try :
			resp = urllib2.urlopen(requestString)
			resp.close() # not interested, if its HTTP OK
		except urllib2.URLError, e:
			log.error("%s returned  %s " % (API_ADD_CHUNK, e))
		
		
	# segmenter shut down for some reason, we don't restart now
	return
	
if __name__ == '__main__':
	
	if len(sys.argv) != 4:
		sys.stderr.write("Usage: segmenter.py xmltvID mcastAddr:port delay\n")
		sys.exit(-1)
	
	while(True):
		process(sys.argv[1], sys.argv[2], sys.argv[3])
