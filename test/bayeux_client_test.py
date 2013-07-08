#!/usr/bin/python
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

from bayeux.bayeux_client import BayeuxClient
import time
import logging

def cb(data):
	print data

def main():
	logging.basicConfig(level=logging.INFO)
	client = BayeuxClient('http://localhost:8080/cometd')
	client.register('/members/demo', cb)
	client.register('/chat/demo', cb)
	client.start()
	time.sleep(500)

if __name__ == '__main__':
	main()