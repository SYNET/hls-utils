# directory where to keep clean files
# under normal conditions, you don't need them
# and this is recommended to mount in RAM
# to hold these temporary files
CLEAN_DIR = '/media/memory'
# where to store encrypted files
ENCRYPTED_DIR = '/media/hls/enc'
# where to look for logs
LOG_DIR = '/media/logs'
# set to True, to keep original FTA files 
# note this should not interfere with RAM-mounted
# CLEAN_DIR, as in this case the clean files won't be removed
# and you'll soon run out of free space on that partition
KEEP_CLEAN = False
# Duration of each segment. 10 seconds is good choice
SEGMENT_DURATION_SECONDS = 10
# how often to rotate AES key (# of segments)
KEY_ROTATE_SEGMENTS = 10 
# should we encrypt or keep clean? 
ENCRYPT	= True
# path to segmentation utility
SEGMENTER_PATH = './live_segmenter'
# path to OpenSSL
OPENSSL_PATH = 'openssl'
# Call to register chunk
API_ADD_CHUNK = 'http://localhost/synet/asset/chunk/add'
# Which part of folder to replace to what, first should be part of ENCRYPTED_DIR
PATH_REPLACE = ['/media/', 'http://192.168.1.27/']
# shared secred
API_KEY = '64cff418758adca1c87d148adeda3144'
