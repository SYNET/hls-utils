#
# This utility runs segmentation / encoding process
# and registers new chunks on the server
# and takes the following arguments
#  segmenterBinary mcastAddr:port /temp/storage/dir /encrypted/storage/dir 
#

#
# CONFIGURATION is imported form settings.py
#
from settings import *

import binascii
import subprocess
from subprocess import PIPE
import logging 
import os, re, sys
import urllib, urllib2

# segmenter: tstamp=1318975595.280000, sequence=98, duration=10.200000, end=0, file=/work/sgm/run2/ts-00098.ts
SEGMENTER_OUTPUT_PATTERN = re.compile("segmenter:\s*tstamp=(?P<startTimeEpoch>[0-9\.]+),\s*sequence=(?P<sequence>[0-9]+),\s*duration=(?P<duration>[0-9\.]+),\s*end=(?P<done>[0-9]),\s*file=(?P<file>\S+)$")

def genKey():
	return binascii.hexlify(subprocess.Popen(['openssl', 'rand', '16'], stdin=None, stderr=None, stdout=PIPE).communicate()[0])

def process(args):
	channelID 	= args[0]
	addr		= args[1]
	delaySeconds= int(args[2])

	log = logging.getLogger('segmenter.py')
	hdlr = logging.FileHandler('segmenter-%s-%s.log'%(channelID, addr.replace(':','_')))
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
	hdlr.setFormatter(formatter)
	log.addHandler(hdlr) 
	log.setLevel(logging.DEBUG)
	
	if not os.path.exists(ENCRYPTED_DIR) or not os.path.isdir(ENCRYPTED_DIR):
		log.error("%s does not exist or is not a folder"%ENCRYPTED_DIR)
		return
	
	if ENCRYPTED_DIR.find(PATH_REPLACE[0]) > 0:
		log.error("REPLACE_PATH %s should be part of %s" % (PATH_REPLACE[0], ENCRYPTED_DIR))
		return
	
	mcastRecvProc = subprocess.Popen([EMCAST_PATH, addr], stdin=None, stdout=PIPE)
	if mcastRecvProc.poll() != None:
		log.error('multicast reception process did not start. abort')
		return
	
	filePrefix = 'ts-%s'%channelID
	segmenterProc = subprocess.Popen([SEGMENTER_PATH, '10', CLEAN_DIR, filePrefix, filePrefix], stdin=mcastRecvProc.stdout, stderr=PIPE)

	if segmenterProc.poll() != None:
		log.error('segmentation process did not start. abort')
		return
	input = segmenterProc.stderr
	#input = sys.stdin
	
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
			log.error("segmenter process terminated");
			break
		

		param = SEGMENTER_OUTPUT_PATTERN.match(out)
		if param is None:
			# could be debug messages, etc - just skipping
			log.warning('cant parse %s '%out)
			continue
		else:
			param = param.groupdict()
		
		encPath		= os.path.normpath(ENCRYPTED_DIR + '/' + os.path.split(param['file'])[1])
		
		# got an output, now encrypt it
		try:
			subprocess.check_call([OPENSSL_PATH, 'aes-128-cbc', '-e', 
				'-in', 	param['file'],
				'-out',	encPath,
				'-nosalt',
				'-K', key,
				'-iv', initVector,
			], stdin=None, stdout=None, stderr=None)
			keyExpire -= 1
		except subprocess.CalledProcessError as e:
			log.error(e)
			break
		
		requestString = API_ADD_CHUNK+'?'+urllib.urlencode({
				'channelID'		 : channelID,
				'appType'		 : '2', # NPVR
				'apiKey'		 : API_KEY,
				'sequence' 		 : param['sequence'],
				'startTimeEpoch' : param['startTimeEpoch'],
				'duration'	 	 : param['duration'],
				'aesKey'		 : key,
				'aesIV' 		 : initVector,
				'file'			 : encPath.replace(PATH_REPLACE[0], PATH_REPLACE[1])
		})
		try :
			resp = urllib2.urlopen(requestString)
			resp.close() # not interested, if its HTTP OK
		except urllib2.URLError, e:
			log.error("%s returned status %s : %s" % (API_ADD_CHUNK, e.code, e.read()))
			return False
		
		if not KEEP_CLEAN:
			os.remove(cleanPath)
		
	# segmenter shut down for some reason, we don't restart now
	return
	
if __name__ == '__main__':
	
	if len(sys.argv) != 4:
		sys.stderr.write("Usage: segmenter.py xmltvID mcastAddr:port delay\n")
		sys.exit(-1)
	
	process(sys.argv[1:])
