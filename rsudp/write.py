import sys, os
from threading import Thread
from queue import Queue
import time
from datetime import datetime, timedelta
from obspy import UTCDateTime
import rsudp.raspberryshake as RS
from rsudp.raspberryshake import qsize
from rsudp.consumer import destinations
from rsudp import printM

class Write(Thread):
	def __init__(self, outdir='', debug=False):
		"""
		Initialize the process
		"""
		super().__init__()
		global destinations

		wrteq = Queue(qsize)
		destinations.append(wrteq)
		self.qno = len(destinations) - 1

		self.stream = RS.Stream()
		self.refcha = None
		self.outdir = outdir
		self.sender = 'Write'
		self.debug = debug
		self.numchns = RS.numchns
		self.stime = 1/RS.sps
		self.inv = RS.inv
		printM('Starting.', self.sender)

	def getq(self):
		d = destinations[self.qno].get(True, timeout=None)
		destinations[self.qno].task_done()
		if 'TERM' in str(d):
			sys.exit()
		self.stream = RS.update_stream(
			stream=self.stream, d=d, fill_value=None)
		if not self.refcha:
			self.refcha = RS.getCHN(d)
		if self.refcha in str(d):
			return True
		else:
			return False
	
	def set_sps(self):
		self.sps = self.stream[0].stats.sampling_rate

	def elapse(self, new=False):
		self.st = UTCDateTime.now()
		self.y, self.m, self.d = self.st.year, self.st.month, self.st.day
		self.j = self.st.strftime('%j')
		self.newday = UTCDateTime(self.y, self.m, self.d + 1, 0, 0)
		if new:
			self.last = self.newday
		else:
			self.last = self.st

	def slicestream(self):
		self.stream.slice(starttime=self.last)

	def write(self, stream=False):
		if not stream:
			self.last = self.stream[0].stats.endtime - timedelta(seconds=5)
			stream = self.stream.copy().slice(
						endtime=self.last, nearest_sample=False)

		for t in stream:
			enc = 'STEIM2'	# encoding
			outfile = self.outdir + '/%s.%s.00.%s.D.%s.%s' % (t.stats.network,
								t.stats.station, t.stats.channel, self.y, self.j)
			if os.path.exists(os.path.abspath(outfile)):
				with open(outfile, 'ab') as fh:
					if self.debug:
						printM('Writing %s records to %s'
								% (len(t.data), outfile), self.sender)
					t.write(fh, format='MSEED', encoding=enc)
			else:
				if self.debug:
					printM('Writing %s new file %s'
							% (len(t.data), outfile), self.sender)
				t.write(outfile, format='MSEED', encoding=enc)

	def run(self):
		"""
		"""
		self.elapse()

		self.getq()
		self.set_sps()
		printM('miniSEED output directory: %s' % (self.outdir), self.sender)
		if self.inv:
			printM('Writing inventory to output directory.', self.sender)
			self.inv.write('%s/%s.%s.00' % (self.outdir,
					self.stream[0].stats.network,
					self.stream[0].stats.station),
					format='STATIONXML')
		printM('Beginning miniSEED output.', self.sender)
		wait_pkts = (self.numchns * 10) / (RS.tf / 1000) 		# comes out to 10 seconds (tf is in ms)

		n = 0
		while True:
			while True:
				if destinations[self.qno].qsize() > 0:
					self.getq()
					time.sleep(0.01)		# wait a few ms to see if another packet will arrive
					n += 1
				else:
					self.getq()
					n += 1
					break
			if n >= wait_pkts:
				if self.newday < UTCDateTime.now(): # end of previous day and start of new day
					self.write(self.stream.slice(
								endtime=self.newday, nearest_sample=False))
					self.stream = self.stream.slice(
								starttime=self.newday, nearest_sample=False)
					self.elapse(new=True)
				else:
					self.write()
					self.stream = self.stream.slice(
								starttime=self.last, nearest_sample=False)
				self.stream = RS.copy(self.stream)
				n = 0

				self.getq()
				time.sleep(0.01)		# wait a few ms to see if another packet will arrive
			sys.stdout.flush()
			sys.stderr.flush()
