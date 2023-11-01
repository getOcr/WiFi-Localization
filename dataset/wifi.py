'''
Descripttion: 
version: 
Contributor: Minjun Lu
Source: Original
LastEditTime: 2023-11-01 20:09:30
'''
import os
import pywt
import math
import cmath
import numpy as np
import torch
import matplotlib.pyplot as plt
from collections.abc import Iterable
from scipy.interpolate import interp1d
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from torch.utils.data import Dataset
from copy import copy,deepcopy
# np.set_printoptions(threshold=np.inf)
PI = 3.1415926
def sgn(num):
    if num > 0.0:
        return 1.0
    elif num == 0.0:
        return 0.0
    else:
        return -1.0

class Frame():
    def __init__(self,timestamp,rx,rssi=None,mcs=None,gain=None) -> None:
        super().__init__()
        self.timestamp = timestamp
        self.rssi = rssi
        self.mcs = mcs
        self.gain = gain
        self.decline = np.sum(gain)-np.sum(rssi)
        self.rx = rx
        if isinstance(rx,Iterable):
            self.amplitude = np.array([abs(i) for i in rx],dtype=np.float32)
            self.phase = np.array([cmath.phase(i) for i in rx],dtype=np.float32)
            # print(self.phase)
            # self.phase = np.angle(rx)
            for i in range(0,len(self.phase),64):
                self.phase[i:i+64] = np.unwrap(self.phase[i:i+64])
        else:
            self.amplitude = abs(rx)
            self.phase = cmath.phase(rx)
        
class WiFi(Dataset):
    def __init__(self,data_file,gt_file=None,sampling_f=96,duration=300,buf=8,
                 window_size=72,stride=1,phase_diff=[0,64],plotting=False) -> None:
        super().__init__()
        
        self.sampling_f = sampling_f
        self.duration = duration
        self.window_size = window_size
        self.stride = stride
        if plotting:
            self.fig, self.ax = plt.subplots(nrows=3,ncols=1,figsize=(18,18), facecolor='white')
            self.ax[0].set_title(os.path.basename(data_file))
        
        # fp = open('/server19/lmj/github/wifi_localization/data/20230918/1.txt','w+')
        self.data:Iterable[Frame]=[]
        with open(data_file,'r') as file:
            for sample in file.readlines():
                sample_list = sample.strip().split()
                for sample_ele in range(0,len(sample_list),12+256):
                    # fp.write(' '.join(sample_list[sample_ele:sample_ele+12+256])+'\n')
                    # print(sample_list[sample_ele+12:sample_ele+12+256])
                    timestamp = np.array(sample_list[sample_ele:sample_ele+3],dtype=np.float32)
                    timestamp = 360 * timestamp[0] + 60 * timestamp[1] + timestamp[2]
                    rssi = np.array(sample_list[sample_ele+3:sample_ele+7],dtype=np.float32)
                    mcs = np.array(sample_list[sample_ele+7],dtype=np.float32)
                    gain = np.array(sample_list[sample_ele+8:sample_ele+12],dtype=np.float32)
                    rx = [i.replace('i','j') for i in sample_list[sample_ele+12:sample_ele+12+256]]
                    rx = np.array(rx,dtype=np.complex128)
                    self.data.append(Frame(timestamp,rx,rssi,mcs,gain))
            file.close()
        self.data = sorted(self.data,key=lambda x:x.timestamp)
        
        amps = []
        for k in range(24,32,1):
            amp = self.filt([i.amplitude[k] for i in self.data])
            timestamps,amp = self.sampling([i.timestamp for i in self.data],amp,sampling_f,duration)
            # amp_mean0 = self.bandpass(amp)
            amp_mean0 = amp-np.mean(amp)
            amp_mean0 = amp_mean0/np.max(amp_mean0)
            amps.append(amp_mean0)
            # self.amp = amp_mean0
        self.amps = np.stack(amps,axis=0)

        
        phases = []
        for k in range(24,32,1):
            phase = np.array([i.phase[k+phase_diff[0]]-i.phase[k+phase_diff[1]] for i in self.data])
            # phase = self.filt([i.phase[k]-i.phase[k+phase_diff] for i in self.data])
            _phase=[]
            for i in phase:
                if i >PI:
                    _phase.append(i-2*PI)
                elif i <= -PI:
                    _phase.append(i+2*PI)
                else:
                    _phase.append(i)
            phase = np.array(_phase)
            
            phase = self.hampel(phase,3)
            phase = signal.savgol_filter(phase,7,3)
            # phase = self.hampel(phase,11)
            # phase = signal.savgol_filter(phase,51,3)
            timestamps,phase = self.sampling([i.timestamp for i in self.data],phase,sampling_f,duration)
            phase_mean0 = phase-np.mean(phase)
            phase_mean0 = phase_mean0/max(np.max(phase_mean0),-1*np.min(phase_mean0))
            phases.append(phase_mean0)
        self.phases = np.stack(phases,axis=0)
        
        # self.draw_all_phase_diff([0,64,128,192])
        
        # declines=[]
        # for i in range(len(self.data)):
        #     if abs(self.data[i].decline)<1000:
        #         declines.append(self.data[i].decline)
        #     else:
        #         declines.append(self.data[0].decline)
        # self.declines = np.array(declines)
        # self.declines = self.hampel(self.declines,3)
        # self.declines = np.expand_dims(self.declines,axis=0) 
        
        # gains = []
        # for k in range(59,60,1):
        #     gain = np.array([i.gain[0] for i in self.data])
        #     timestamps,gain = self.sampling([i.timestamp for i in self.data],gain,sampling_f,duration)
        #     gain_mean0 = gain-np.mean(gain)
        #     gain_mean0 = gain_mean0/np.max(abs(gain_mean0))
        #     gains.append(gain_mean0)
        # self.gains = np.stack(gains,axis=0)
        
        # rssis = []
        # for k in range(59,60,1):
        #     rssi = np.array([i.rssi[0] for i in self.data])
        #     timestamps,rssi = self.sampling([i.timestamp for i in self.data],rssi,sampling_f,duration)
        #     rssi_mean0 = rssi-np.mean(rssi)
        #     rssi_mean0 = rssi_mean0/np.max(abs(rssi_mean0))
        #     rssis.append(rssi_mean0)
        # self.rssis = np.stack(rssis,axis=0)
        
        if plotting:
            self.ax[0].plot(timestamps, self.amps[-1], color='b',linestyle='-',label='amplitude')
            self.ax[1].plot(timestamps, self.phases[-1], color='b',linestyle='-',label='phase')
            # self.ax[2].plot([i.timestamp for i in self.data], self.declines[-1], color='b',linestyle='-',label='decline')
            self.ax[0].set_title('amplitude(high-pass)')
            self.ax[1].set_title('phase_diff')
            self.ax[2].set_title('energy_decline')
        
        self.gt_bin = self.gt = None
        
        if gt_file:
            with open(gt_file) as gt:
                self.gt = np.array(gt.readline().strip().split(), dtype=np.float32)
                gt.close()
            self.gt_window=2
            self.gt = self.gt[:duration//self.gt_window]
            inter0 = np.linspace(0, duration, duration//self.gt_window)
            fc = interp1d(inter0, self.gt, kind='nearest',axis=0)
            inter = np.linspace(0, duration, sampling_f*duration)
            self.gt = fc(inter)
            self.gt_diff = self.diff(self.gt)
            self.gt_wavelet = self.wavelet(self.gt_diff,buf=buf*sampling_f)
            self.gt_gauss=gaussian_filter1d(self.gt_wavelet, sigma=sampling_f*1.5)
            self.gt_bin=np.array([int(i!=0) for i in self.gt])
            
            if plotting:
                self.ax[0].plot(inter, self.gt, color='r',linestyle='-',label='gt')
                self.ax[1].plot(inter, self.gt, color='r',linestyle='-',label='gt')
                self.ax[0].plot(inter, self.gt_bin, color='r',linestyle='--',label='gt_bin')
                self.ax[1].plot(inter, self.gt_bin, color='r',linestyle='--',label='gt_bin')
                # self.ax.plot(inter, self.gt_diff, color='m',linestyle='-',label='diff')
                # self.ax.plot(inter, self.gt_wavelet, color='c',linestyle='-.',label='wavelet')
                # self.ax.plot(inter, self.gt_gauss, color='g',linestyle='-.',label='gauss')
        if plotting:
            plt.xlabel('Time')
            plt.ylabel('Value')
            self.fig.legend(loc='upper right')
            self.fig.savefig('dataset.jpg')
    
    def unwrap(self,l:np.ndarray):
        _l = deepcopy(l)
        new_l = np.zeros_like(_l)
        for i in range(len(_l)):
            if i ==0:
                new_l[i]=_l[i]
            elif _l[i]-_l[i-1]>PI:
                _l[i:]=_l[i:]-2*PI
                new_l[i]=_l[i]
            elif _l[i]-_l[i-1]<-PI:
                _l[i:]=_l[i:]+2*PI
                new_l[i]=_l[i]
            else:
                new_l[i]=_l[i]
        print(l[5:],new_l[5:])
        return new_l
    
    def draw_all_phase_diff(self,l:list):
        count=0
        for j1 in range(len(l)-1):
            for j2 in range(j1+1,len(l)):
                count+=1
        fig, ax = plt.subplots(nrows=count,ncols=1,figsize=(24,24), facecolor='white')
        count=0
        for j1 in range(len(l)-1):
            for j2 in range(j1+1,len(l)):
                print(l[j1],l[j2])
                phases = []
                for k in range(15,16,1):
                    p1 = np.array([i.phase[k+l[j1]] for i in self.data])
                    p2 = np.array([i.phase[k+l[j2]] for i in self.data])
                    phase = p1-p2
                    # phase = np.array([i.phase[k+l[j1]]-i.phase[k+l[j2]] for i in self.data])
                    # phase = self.filt([i.phase[k]-i.phase[k+phase_diff] for i in self.data])
                    
                    _phase=[]
                    for i in phase:
                        if i >PI:
                            _phase.append(i-2*PI)
                        elif i <= -PI:
                            _phase.append(i+2*PI)
                        else:
                            _phase.append(i)
                    phase = np.array(_phase)
                    
                    phase = self.hampel(phase,5)
                    phase = signal.savgol_filter(phase,7,3)


                    timestamps,phase = self.sampling([i.timestamp for i in self.data],phase,self.sampling_f,self.duration)
                    # phase = self.bandpass(phase)
                    # phase_mean0 = phase-np.mean(phase)
                    # phase_mean0 = phase_mean0/max(np.max(phase_mean0),-1*np.min(phase_mean0))
                    # phase_mean0 = phase_mean0/np.max(phase_mean0)
                    phases.append(phase)
                ax[count].plot(timestamps, phases[-1], color='b',linestyle='-',label='phase')
                ax[count].set_title('{0}-{1}'.format(l[j1],l[j2]))
                count+=1
        fig.savefig('phase.jpg')
                
    def hampel(self,X,k):
        length = X.shape[0] - 1
        nsigma = 3
        iLo = np.array([i - k for i in range(0, length + 1)])
        iHi = np.array([i + k for i in range(0, length + 1)])
        iLo[iLo < 0] = 0
        iHi[iHi > length] = length
        xmad = []
        xmedian = []
        for i in range(length + 1):
            w = X[iLo[i]:iHi[i] + 1]
            medj = np.median(w)
            mad = np.median(np.abs(w - medj))
            xmad.append(mad)
            xmedian.append(medj)
        xmad = np.array(xmad)
        xmedian = np.array(xmedian)
        scale = 1.4826  # 缩放
        xsigma = scale * xmad
        xi = ~(np.abs(X - xmedian) <= nsigma * xsigma)  # 找出离群点（即超过nsigma个标准差）
    
        # 将离群点替换为中为数值
        xf = X.copy()
        xf[xi] = xmedian[xi]
        return xf

    
    def diff(self,sig):
        return np.diff(sig,prepend=sig[0:1])
    def wavelet(self,sig,buf,clip=None):
        aftershock = np.zeros_like(sig)
        for i,gt in enumerate(sig):
            new = np.zeros_like(sig)
            if gt==0:
                continue
            elif gt>0:
                kernel = min(int(buf),len(sig)-i-1)
                new[i+1:i+kernel+1]=gt
                new[i-kernel//3:i]=gt
            elif gt<0:
                kernel = min(int(buf),i)
                new[i+1:i+kernel//3+1]=gt
                new[i-kernel:i]=gt
            # else:
            #     kernel = min(buf//2,i)
            #     new[i-kernel:i]=gt
            #     new[i+1:i+kernel+1]=gt
            aftershock=aftershock+new
        if clip:
            return np.clip(sig+aftershock,-clip,clip)
        else:
            return sig+aftershock
        
    def medfilt(self,iter,kernel_size=5):
        padding=(kernel_size-1)//2
        iter = [iter[0]]*padding+iter+[iter[-1]]*padding
        res = []
        for i in range(len(iter)-2*padding):
            _res = iter[i:i+kernel_size]
            _res.sort(key=lambda x:abs(x))
            res.append(_res[padding])
        return res
    def filt(self,iter):
        mean = np.mean(iter)
        std = np.std(iter)
        res = []
        for i in iter:
            if i>mean+5*std or i<mean-5*std:
                res.append(mean)
            else:
                res.append(i)
        return res

    def sampling(self,timestamp,data,sampling_f,duration):
        fc = interp1d(timestamp, data, kind='slinear',axis=0)
        timestamps = np.linspace(0, duration, num=sampling_f*duration, endpoint=False)
        new_data = np.array(fc(timestamps))
        return timestamps,new_data
        
    def bandpass(self,x:np.ndarray):
        # from kalman import Kalman_Filter
        # A = 0.1
        # H = 1
        # Q = 0.5
        # R = 0.5
        # x[0]=0
        # kf1 = Kalman_Filter(A, H, Q, R, x[np.newaxis,:].T)   # 不加反馈
        # xb = 50
        # Pb = 1
        # x1 = kf1.get_filtered_data(xb, Pb)
        # return x1

        b, a = signal.butter(8,0.05,'highpass')
        x_filter = signal.filtfilt(b,a,x)
        b, a = signal.butter(8,0.6,'lowpass')
        x_filter = signal.filtfilt(b,a,x_filter)
        return x_filter
        
    def __len__(self):
        return int((self.duration-self.window_size)/self.stride)+1
    def __getitem__(self, index):
        start = int(index*self.stride)
        end = int(index*self.stride+self.window_size)
        timestamp = [start,end]
        amp = self.amps[:,int(index*self.stride*self.sampling_f):int((index*self.stride+self.window_size)*self.sampling_f)]
        amp = torch.from_numpy(amp).float()
        phase = self.phases[:,int(index*self.stride*self.sampling_f):int((index*self.stride+self.window_size)*self.sampling_f)]
        phase = torch.from_numpy(phase).float()
        data = torch.concat((amp,phase),dim=0)
        if self.gt is not None and self.gt_bin is not None:
            label2 = self.gt[int(index*self.stride*self.sampling_f):int((index*self.stride+self.window_size)*self.sampling_f):24]
            label1 = self.gt_bin[int(index*self.stride*self.sampling_f):int((index*self.stride+self.window_size)*self.sampling_f):24]
            return timestamp,data,torch.from_numpy(label1),torch.from_numpy(label2)
        else:
            return timestamp,data,-1,-1
    
class MultiWiFi(Dataset):
    def __init__(self,dir_list,filename,gt_file) -> None:
        super().__init__()
        self.datalist = [WiFi(os.path.join(dir,filename),gt_file) for dir in dir_list]
    def __len__(self):
        return len(self.datalist[0])
    def __getitem__(self, index):
        setlist=[]
        for subset in self.datalist:
            timestamp,data,label = subset[index]
            setlist.append(data)
        return timestamp,torch.concat(setlist,dim=0),label
            
        

if __name__=='__main__':
    # dataset = WiFi(data_file = '/server19/lmj/github/wifi_localization/data/20230918/room3/csi_2023_09_11_15_14.txt',
    #                gt_file = '/server19/lmj/github/wifi_localization/data/20230918/room3-gt/csi_2023_09_11_15_14.txt')
    dataset = WiFi(data_file = '/server19/lmj/github/wifi_localization/data/20231016/room1/AP2/data/csi_2023_10_16_1.txt',
                   gt_file = '/server19/lmj/github/wifi_localization/data/20231016/room1/AP2/truth/csi_2023_10_16_1_truth.txt',
                   phase_diff=[0,64])
    print(dataset[0])