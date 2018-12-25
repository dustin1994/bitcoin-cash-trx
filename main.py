#!/usr/bin/env python

import sys
import os
import binascii
import ecdsa
import hashlib
import struct
import base58
import time
import socket
from hexdump import hexdump
import requests

################################# KEY / ADDRESS GENERATION ###################################
# https://en.bitcoin.it/wiki/Base58Check_encoding

def doubleSHA256(data):
	return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def base58CheckEncoding(version, payload):
	keyBytes = version + payload
	# Calculating the checksum with double SHA-256 (take 4 first bytes of the result)
	doubleSHA256Hash = doubleSHA256(keyBytes)
	# Address = Base58(HashedPublicKey + checksum)
	checksum = doubleSHA256Hash[:4]
	return base58.b58encode(keyBytes + checksum)

def base58CheckDecoding(payload):
	result = base58.b58decode(payload)[0:-4]
	return result[1:]
 
def privateKey256():
	# 256-bit private key
	return os.urandom(32)

def privateKeyToWif(secretKeyBytes):    
	return base58CheckEncoding('\x80', secretKeyBytes + '\x01')  

def wifToPrivateKey(wifPrivateKey):
	return base58CheckDecoding(wifPrivateKey)[:-1] 
	    
def privateKeyToPublicKey(secretKeyBytes):
	key = ecdsa.SigningKey.from_string(secretKeyBytes, curve=ecdsa.SECP256k1).verifying_key
	keyBytes = key.to_string()
	# 512-bit public key with prefix '04'
	return '\x04' + keyBytes 

def privateKeyToCompressedPublicKey(secretKeyBytes):
	key = ecdsa.SigningKey.from_string(secretKeyBytes, curve=ecdsa.SECP256k1).verifying_key
	keyBytes = key.to_string()
	keyHex = binascii.hexlify(keyBytes)
	keyStr = keyHex.decode('utf-8')
	halfLen = len(keyHex) // 2
	keyHalf = keyHex[:halfLen]
	# Add bitcoin byte: 0x02 if the last digit is even, 0x03 if the last digit is odd
	lastByte = int(keyStr[-1], 16)
	bitcoinByte = '\x02' if lastByte % 2 == 0 else b'\x03'
	publicKey = bitcoinByte + binascii.unhexlify(keyHalf)
	return publicKey
	 
def pubKeyToAddr(publicKeyBytes):
	# 160-bit Hashed public key & Add the netwok byte 0x00 for main network
	# 0x6f for test network
	ripemd160 = hashlib.new('ripemd160')
	ripemd160.update(hashlib.sha256(publicKeyBytes).digest())
	return base58CheckEncoding('\x00', ripemd160.digest())

def addressToScriptPubKey(address):
	# OP_DUP OP_HASH160 (20 bytes) OP_EQUALVERIFY OP_CHECKSIG
	# 76 A9 14 (20 bytes) 88AC
	return '76a914' + binascii.hexlify(base58CheckDecoding(address)) + '88ac'	

privateKey = privateKey256()
publicKey = privateKeyToCompressedPublicKey(privateKey)
wifPrivateKey = privateKeyToWif(privateKey)
address = pubKeyToAddr(publicKey)
print binascii.hexlify(privateKey)
print binascii.hexlify(publicKey)
print wifPrivateKey
print address
print binascii.hexlify(wifToPrivateKey(wifPrivateKey))
print '\n'
################################# TRANSACTION GENERATION ###################################
# For a waklthrough check the answer in this thread : https://bitcoin.stackexchange.com/questions/3374/how-to-redeem-a-basic-tx
#HEX_PREVIOUS_TRX = 'a561cf6e8d347f5e441daafcb688d70d7b332d5601d243a503bdba4345e78276'
HEX_PREVIOUS_TRX = '9ce36975caacacce9990f3c11b5967e64feac1de956df1ad5c0c49fdadcd01da'
RECEIVER_ADDR = '15QCoirrat6PRNunChbnyuKMXvDnjBrgP5'
SENDER_ADDR=address
#SENDER_ADDR = ''
AMOUNT_TO_SEND = 0.00001000
AMOUNT_TO_KEEP = 0.68790000 
#WIF_PRIVATE_KEY= ''
WIF_PRIVATE_KEY=wifPrivateKey

def convertBCHtoSatoshi(bch):
	return bch * 10**8

def formatOutput(output):
	scriptPubKey, value = output
	return (binascii.hexlify(struct.pack('<Q', value))
		+ '%02x' % len(scriptPubKey.decode('hex'))
		+ scriptPubKey)

def generateRawTransaction(prevOutputHash, prevOutputIdx, scriptSig, outputs):
	return  ( '01000000' 
			+ '01'
			+ binascii.hexlify(prevOutputHash.decode('hex')[::-1])
			+ binascii.hexlify(struct.pack('<L', prevOutputIdx))
			+ '%02x' % len(scriptSig.decode('hex'))
			+ scriptSig
			+ 'ffffffff'
			+ '%02x' % len(outputs)
			+ ''.join(map(formatOutput, outputs)) 
			+ '00000000'
			)
def generateSignedTransaction(privateKey, prevOutputHash, prevOutputIdx, scriptPubKey, outputs):
	trxToSign = generateRawTransaction(prevOutputHash, prevOutputIdx, scriptPubKey, outputs) + '01000000'
	print '\n' + trxToSign + '\n'
	hashTrxToSign = doubleSHA256(trxToSign)
	#create a public/private key pair out of the provided private key
	sk = ecdsa.SigningKey.from_string(privateKey, curve=ecdsa.SECP256k1)
	#sign the hash from step with the secret key
	trxSignature = sk.sign_digest(hashTrxToSign, sigencode=ecdsa.util.sigencode_der) + '\01'
	pk = privateKeyToPublicKey(privateKey)
	'''
	Construct the final scriptSig by concatenating : 
	- One-byte script OPCODE containing the length of the DER-encoded signature plus 1 (the length of the one-byte hash code type)
	- The actual DER-encoded signature plus the one-byte hash code type
	- One-byte script OPCODE containing the length of the public key
	- The actual public key
	'''
	scriptSig = binascii.hexlify(chr(len(trxSignature)) + trxSignature) + binascii.hexlify(chr(len(pk)) + pk)
	print scriptSig
	signedTrx = generateRawTransaction(prevOutputHash, prevOutputIdx, scriptSig, outputs)
	return signedTrx

def makeTransaction(WIFPrivateKey, prevTrxHash, prevOutputIdx, senderPublicKey, receivers):
	#convert WIF to private key
	privateKey = wifToPrivateKey(WIFPrivateKey)
	print binascii.hexlify(privateKey)
	signedTrx = generateSignedTransaction(privateKey, prevTrxHash, prevOutputIdx, senderPublicKey, receivers)
	print 'Signed Transaction : ' + signedTrx
	return signedTrx

outputs = [(addressToScriptPubKey(RECEIVER_ADDR), convertBCHtoSatoshi(AMOUNT_TO_SEND)), (addressToScriptPubKey(SENDER_ADDR), convertBCHtoSatoshi(AMOUNT_TO_KEEP))]

signedTrx = makeTransaction(WIF_PRIVATE_KEY, HEX_PREVIOUS_TRX, 1, addressToScriptPubKey(SENDER_ADDR), outputs)

################################# SEND TRANSACTION FOR MINING  ###################################
# https://en.bitcoin.it/wiki/Protocol_documentation
#4 	magic 		uint32_t 	Magic value indicating message origin network, and used to seek to next message when stream state is unknown
#12 command 	char[12] 	ASCII string identifying the packet content, NULL padded (non-NULL padding results in packet rejected)
#4 	length 		uint32_t 	Length of payload in number of bytes
#4 	checksum 	uint32_t 	First 4 bytes of sha256(sha256(payload))
#? 	payload 	uchar[] 	The actual data 
MAGIC_MAIN=0xD9B4BEF9
MAGIC_TEST_NET=0xDAB5BFFA
MAGIC_TEST_NET3=0x0709110B
BUFFER_SIZE=4096
MAGIC_BCH=0xe8f3e1e3

def processVarInt(payload):
	n0 = ord(payload[0])
	if n0 < 0xfd:
		return [n0, 1]
	elif n0 == 0xfd:
		return [struct.unpack('<H', payload[1:3])[0], 3]
	elif n0 == 0xfe:
		return [struct.unpack('<L', payload[1:5])[0], 5]
	else:
		return [struct.unpack('<Q', payload[1:5])[0], 7]

def processVarStr(payload):
	n, length = processVarInt(payload)
	return [payload[length:length+n], length + n]

# takes 26 byte input, returns string  
def processAddr(payload):
	assert(len(payload) >= 26)
	return '%d.%d.%d.%d:%d' % (ord(payload[20]), ord(payload[21]), ord(payload[22]), ord(payload[23]), struct.unpack('!H', payload[24:26])[0])

addrCount = 0
def processChunk(header, payload):
	""" Processes a response from a peer."""
	magic, cmd, payload_len, checksum = struct.unpack('<L12sL4s', header)
	if len(payload) != payload_len:
		print 'BAD PAYLOAD LENGTH', len(payload), payload_len
        
	cmd = cmd.replace('\0', '') # Remove null termination
	print '--- %s ---' % cmd
    
	if cmd == 'version':
		version, services, timestamp, addr_recv, addr_from, nonce = struct.unpack('<LQQ26s26sQ', payload[:80])
		agent, agent_len = processVarStr(payload[80:])

		start_height = struct.unpack('<L', payload[80 + agent_len:84 + agent_len])[0]
		print '%d %x %x %s %s %x %s %x' % (version, services, timestamp, processAddr(addr_recv), processAddr(addr_from), nonce, agent, start_height)
	elif cmd == 'inv':
		count, offset = processVarInt(payload)
		result = []
		for i in range(0, count):
			type, hash = struct.unpack('<L32s', payload[offset:offset+36])
			# Note: hash is reversed
			print type, hash[::-1].encode('hex')
			if type == 2:
				sys.exit(0)
				result.append([type, hash])
		offset += 36
		print '---\n'
		return result
	elif cmd == 'addr':
		global addrCount
		count, offset = processVarInt(payload)
		for i in range(0, count):
			timestamp, = struct.unpack('<L', payload[offset:offset+4])
			addr = processAddr(payload[offset+4:offset+30])
			offset += 30
			print addrCount, time.ctime(timestamp), addr
			addrCount += 1
	else:
		hexdump(payload)
	print '---\n'


def sockRead(sock, count):
	data = b''
	while len(data) < count:
		data += sock.recv(count - len(data))
	return data

def recvMsg(sock):
	header = sockRead(sock, 24)
	magic, command, payloadLen, checksum = struct.unpack('<L12sL4s', header)
	payload = sockRead(sock, payloadLen)
	processChunk(header, payload)
	return command, payload
	
# Variable length Integer
def varint(intData):
	if intData < 0xfd:
		return struct.pack('<B', intData)
	elif intData < 0xffff:
		return struct.pack('<cH', '\xfd', intData)
	elif intData < 0xffffffff:
		return struct.pack('<cL', '\xfe', intData)
	else:
		return struct.pack('<cQ', '\xff', intData)

# Variable length String
def varstr(strData):
	return varint(len(strData)) + strData

def netaddr(ipaddr, port, timestamp=True):
	services = 1
	return (struct.pack('<Q12s', services, '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff') +
struct.pack('>4sH', ipaddr, port))

def createMsg(command, payload):
	checksum = doubleSHA256(payload)[0:4]
	return struct.pack('I12sI4s', MAGIC_BCH, command, len(payload), checksum) + payload

def createVersionMsg():
	version = 180002
	services = 1
	timestamp = int(time.time())
	addrRecv = netaddr(socket.inet_aton('127.0.0.1'), 8333, False)
	addrFrom = netaddr(socket.inet_aton('127.0.0.1'), 8333, False)
	nonce = struct.unpack('<Q', os.urandom(8))[0]
	userAgent = varstr('')
	startHeight = 0
	payload = struct.pack('<LQQ26s26sQsL', version, services, timestamp, addrRecv, addrFrom, nonce, userAgent, startHeight)
	return createMsg('version', payload)

def createInvMsg(trxHash):
	payload = varint(1) + struct.pack('<L', 2) + binascii.unhexlify(trxHash)[::-1]
	return createMsg('getdata', payload)

def createTrxMsg(trxHex):
	return createMsg('tx', trxHex)

if __name__ == '__main__':
	# Get peers
#	rawData = requests.get(url='https://api.blockchair.com/bitcoin-cash/nodes').json()
#	peers = [x.split(':')[0] for x in rawData['data']['nodes'].keys()]
	peers = socket.gethostbyname_ex('seed.bitcoinabc.org')[2]
	for peer in peers:
		try:
			print 'Sending message to : %s' % peer
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			#sock.settimeout(5.0)
			sock.connect((peer, 8333))
			sock.send(createVersionMsg())
			command, payload = recvMsg(sock)
			print 'Command: %s - Payload: %d -> %s' % (command, len(payload), binascii.hexlify(payload))
			break
		except Exception as e:
			print e
			continue
	cmd, payload = recvMsg(sock)
	sock.send(createMsg('verack', ''))
	
	#sock.send(createTrxMsg(binascii.unhexlify(signedTrx)))
	sock.send(createInvMsg('683a674017c7c3137ca3b65cca928c0a8da35dc1252b6f98931d2f3405d8038a'))	
	while not cmd.decode().startswith('block'):
		cmd, payload = recvMsg(sock)

	print len(payload)
	print varint(payload[80:])
