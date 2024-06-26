import os
import glob
import random
import argparse
import builtins
import numpy as np
from tqdm import tqdm
from collections import OrderedDict
import torch
import torch.nn as nn
import torch.optim as optim
import torch.distributed as dist
import torch.backends.cudnn as cudnn
from torch.utils.data import DataLoader, ConcatDataset, random_split
from torch.autograd import Variable
from scipy import signal
import matplotlib.pyplot as plt

from config.cfg import Config
from dataset.wifi import WiFi

from model.net import Model
from utils.logger import Log
from utils.meter import AverageMeter
from utils.gradualwarmup import GradualWarmupScheduler

answer = open('/server19/lmj/github/wifi_localization/predict/2_office_44.txt','w')
TASK = 'task2'
M=6+1
Threshold = 0.5
R=2

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    
cfg = Config('/server19/lmj/github/wifi_localization/config/config.yaml')
config = cfg()
config['model_name']='/server19/lmj/github/wifi_localization/run/v4.4'
set_seed(config['seed'])

device = torch.device('cuda',0)
model = Model().to(device)

new_state_dict = OrderedDict()
state_dict = torch.load(os.path.join(config['model_save_dir'],config['model_name'],'best.pth'),map_location = 'cpu')

for k, v in state_dict.items():
    if k in model.state_dict().keys():
        new_state_dict[k] = v
    elif k[7:] in model.state_dict().keys():
        new_state_dict[k[7:]] = v
    else:
        continue
model.load_state_dict(new_state_dict)
print('loading pre-trained model from {0}'.format(os.path.join(config['model_save_dir'],config['model_name'],'best.pth')))

dataset_list = []
for room in range(0,4):
    for i in range(1,M):
        file_name = os.path.join('/server19/lmj/github/wifi_localization/data/test',TASK,'room'+str(room),'data','csi_2023_10_31_'+str(i)+'.txt')
        print(file_name)

        test_data = WiFi(data_file=file_name,
                                    stride=2,
                                    subcarrier=config['subcarrier'],
                                    window_size=config['window_size'])

        test_loader = DataLoader(test_data,
                                batch_size=1,
                                num_workers=1,
                                pin_memory=True,
                                )
        with torch.no_grad():
            count = np.zeros([300*R])
            score_man = np.zeros([300*R])
            score_num = np.zeros([300*R])
            model.eval()
            with tqdm(total=len(test_loader),desc='test',ncols=100) as valbar:
                for batch_idx,data in enumerate(test_loader):
                    timestamp, csi, gt_manned,gt_numhuman = data
                    csi = csi.to(device)

                    preds_manned, preds_numhuman = model(csi)
                    start = timestamp[0].item()
                    end = timestamp[1].item()

                    
                    # _,preds_manned = preds_manned.max(1)
                    x = preds_manned[:,0,:].cpu().numpy()
                    y = preds_manned[:,1,:].cpu().numpy()
                    preds_manned  = torch.from_numpy(np.select(y>=Threshold,np.ones_like(y),np.zeros_like(y)))
                    for pred_man,pred_num in zip(preds_manned,preds_numhuman):
                        _count = np.zeros_like(count)
                        _count[start*R:end*R]=1
                        count = count+_count
                        
                        _score = np.zeros_like(score_man)
                        _score[start*R:end*R]=pred_man.cpu().numpy()
                        score_man+=_score
                        
                        _score = np.zeros_like(score_num)
                        _score[start*R:end*R]=pred_num.cpu().numpy()
                        score_num+=_score
                    
                    valbar.update(1)  

            predict_man = score_man / count
            predict_man = [round(i) for i in predict_man]
            predict_man = [round(np.mean(np.array(predict_man[i:i+R*2]))) for i in range(0,len(predict_man),R*2)]
            predict_man = signal.medfilt(predict_man,5)
            
            predict_num = score_num / count
            predict_num = [round(i) for i in predict_num]
            predict_num = [round(np.mean(np.array(predict_num[i:i+R*2]))) for i in range(0,len(predict_num),R*2)]

            # for i in range(len(predict_man)):
            #     if predict_man[i]==1 and predict_num[i]>=1:
            #         predict_man[i] = predict_num[i]
            # if 0 not in predict_man:
            #     predict_man -= 1
            print(predict_man)
            predict_man = [str(p) for p in predict_man]
            predict_man = ' '.join(predict_man)
            answer.write(predict_man+'\n')
            