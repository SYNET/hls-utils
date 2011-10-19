# directory where to keep clean files
CLEAN_DIR = '/tmp/segments'
# where to store encrypted files
ENCRYPTED_DIR = '/tmp/enc'
# set to True, to keep original FTA files 
KEEP_CLEAN = False
# how often to rotate AES key (# of segments)
KEY_ROTATE_SEGMENTS = 10 
# should we encrypt ot keep open? 
ENCRYPT	= True
# path to utility joining multicast group and providing output to stdout
EMCAST_PATH = 'emcast'
# path to segmentation utility
SEGMENTER_PATH = 'live_segmenter'
# path to OpenSSL
OPENSSL_PATH = 'openssl'
# Call to register chunk
API_ADD_CHUNK = 'http://localhost:8000/synet/asset/chunk/add'
# Which part of folder to replace to what, first should be part of ENCRYPTED_DIR
PATH_REPLACE = ['/tmp/enc', 'http://localhost/enc']
# shared secred
API_KEY = 'synet'