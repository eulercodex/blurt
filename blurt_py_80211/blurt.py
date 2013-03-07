#!/usr/bin/env python
import numpy as np
import sys
import audioLoopback, channelModel, maskNoise, wifi80211
import audio, audio.stream
import pylab as pl

wifi = wifi80211.WiFi_802_11()

fn = '35631__reinsamba__crystal-glass.wav'
Fs = 48000.
Fc = 16000. #Fs/4
upsample_factor = 8
mask_noise = maskNoise.prepareMaskNoise(fn, Fs, Fc, upsample_factor)
mask_noise = mask_noise[:int(Fs)]
mask_noise[int(Fs*.5):] *= 1-np.arange(int(Fs*.5))/float(Fs*.5)
lsnr = None
rate = 0
length = 32

def test(visualize=False):
    input_octets = np.random.random_integers(0,255,length)
    output = wifi.encode(input_octets, rate)
    if lsnr is not None:
        input = channelModel.channelModel(output, lsnr)
        bitrate = None
    elif Fs is not None:
        input = audioLoopback.audioLoopback(output, Fs, Fc, upsample_factor, mask_noise)
        bitrate = input_octets.size*8 * Fs / float(output.size) / upsample_factor
    try:
        results, _ = wifi.decode(input, visualize)
        return len(results), bitrate
    except Exception, e:
        print e
        return False, bitrate

def transmit(message):
    length = len(message)
    input_octets = np.array(map(ord, message))
    output = wifi.encode(input_octets, rate)
    audioLoopback.audioOut(output, Fs, Fc, upsample_factor, mask_noise)

def presentResults(results, drawFunc):
    _results = results
    _drawFunc = drawFunc
    def f():
        for result in _results:
            payload, _, _, lsnr_estimate = result
            print repr(''.join(map(chr, payload))) + (' @ %.1f dB' % lsnr_estimate)
        needRedraw = False
        if drawFunc is not None:
            pl.figure(1)
            drawFunc()
            needRedraw = True
        if needRedraw:
            pl.draw()
    return f

badPacketWaveforms = []

class ContinuousReceiver(audioLoopback.AudioBuffer):
    def init(self):
        self.kwargs['maximum'] = int(Fs*3)
        self.kwargs['trigger'] = int(Fs)
        super(ContinuousReceiver, self).init()
    def trigger_received(self):
        input = self.peek(self.maximum)
        #print '%.0f%%' % ((float(self.length)/self.maximum) * 100)
        #print '\r\x1b[K' + ('.' * int(30 + 10*np.log10(np.var(input)))),
        endIndex = 0
        visualize = False
        try:
            input = audioLoopback.processInput(input, Fs, Fc, upsample_factor)
            results, drawFunc = wifi.decode(input, visualize, visualize)
            for result in results:
                _, startIndex, endIndex, _ = result
            if len(results):
                self.onMainThread(presentResults(results, drawFunc))
            else:
                print 'Saving waveform'
                badPacketWaveforms.append(input)
        except Exception, e:
            print repr(e)
        if endIndex:
            return endIndex*upsample_factor
        else:
            return self.trigger/2

class ContinuousTransmitter(audio.stream.ThreadedStream):
    def thread_produce(self):
        input_octets = ord('A') + np.random.random_integers(0,25,length)
        output = wifi.encode(input_octets, rate)
        output = audioLoopback.processOutput(output, Fs, Fc, upsample_factor, None)
        return output[:,0]

def startListening():
    audio.record(ContinuousReceiver(), Fs)

def startTransmitting():
    audio.play(ContinuousTransmitter(), Fs)

def decoderDiagnostics(waveform=None):
    if waveform is None:
        waveform = badPacketWaveforms[-1]
    Fs_eff = Fs/upsample_factor
    ac = wifi.autocorrelate(waveform)
    ac_t = np.arange(ac.size)*16/Fs_eff
    synch = wifi.synchronize(waveform, True)/float(Fs_eff)
    pl.figure(2)
    pl.clf()
    pl.subplot(211)
    pl.specgram(waveform, NFFT=64, noverlap=64-1, Fc=Fc, Fs=Fs_eff, interpolation='none', window=lambda x:x)
    pl.xlim(0, waveform.size/Fs_eff)
    yl = pl.ylim(); pl.vlines(synch, *yl); pl.ylim(*yl)
    pl.subplot(212)
    pl.plot(ac_t, ac)
    pl.plot(ac_t, -ac*np.r_[0,np.diff(ac,2),0]*100)
    yl = pl.ylim(); pl.vlines(synch, *yl); pl.ylim(*yl)
    pl.xlim(0, waveform.size/Fs_eff)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == '--rx':
            try:
                startListening()
            except KeyboardInterrupt:
                pass
            decoderDiagnostics()
        elif sys.argv[1] == '--tx':
            startTransmitting()
