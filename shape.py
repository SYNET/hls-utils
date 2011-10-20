#
# keeps an eye on growing output folder size
# and removes oldest data
#

from settings import *
import os, os.path

GB = 1024*1024*1000

if __name__=='__main__':
	#print('Monitoring %s to have cap of %d gigabytes'%(ENCRYPTED_DIR, MAX_SIZE_GB))
	
	root, dirs, files = os.walk(ENCRYPTED_DIR)
	
	files.sort(key= lambda x : os.path.getsize(x))
	
	print files