import os
import time
import pickle
import sys

import timm
from torch.utils.data import Dataset 
from torch.utils.data.sampler import WeightedRandomSampler

import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
from torch.utils.tensorboard import SummaryWriter
import matplotlib.pyplot as plt

import LRSchedules
from train import train_model
import visualisation
from eyePACS import EyePACS_Dataset

#testing
import numpy as np
from torchvision import transforms, datasets

if __name__ == "__main__":
    # Set up directory for experiment
    model_name = "resnet50"
    dataset_name = "_eyePACS_"
    run_directory = os.path.join("runs", model_name+ dataset_name + time.strftime("%m_%d_%H_%M_%S"))
    os.mkdir(run_directory)

    # Load datasets split into train, val and test
    dataset_names = ["train", "val", "test"]
    data_directory = "diabetic-retinopathy-detection" 
    # data_directory = sys.argv[1]
    dataset_proportions = np.array([0.6, 0.2, 0.2])
    full_dataset = EyePACS_Dataset(data_directory, max_length=1000, random_state=13)
    class_names = full_dataset.class_names

    datasets = full_dataset.create_train_val_test_datasets(dataset_proportions, dataset_names)
    datasets["train"].augment=True
    
    # with open(os.path.join(run_directory, "dataset_indexes.pkl"), "wb+") as index_file:
    #     pickle.dump(dataset_indicies, index_file)

    # Setup dataloaders
    batch_size= 64
    num_workers = 4
    dataset_sizes = {name: len(datasets[name]) for name in dataset_names}                  
    dataloaders = {name: torch.utils.data.DataLoader(datasets[name], batch_size=batch_size,
                                            shuffle=False, num_workers=num_workers)
                        for name in dataset_names}   
    dataloaders["train"].shuffle = True

    # Calc class inbalance and so loss function weights
    data_train_labels = datasets["train"].get_labels()

    train_freq = torch.tensor(data_train_labels.value_counts(sort=False).sort_index()).float()
    weight = 1.0/train_freq
    weight = weight / torch.sum(weight) * len(class_names)

    # Set hyperparameters
    num_epochs = 100
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = timm.create_model(model_name, pretrained=True, num_classes=len(class_names), drop_rate=0.5).to(device)
    criterion = nn.CrossEntropyLoss(weight=weight.to(device))
    optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9, weight_decay=0.0005)
    warmup_steps = 10
    scheduler = LRSchedules.WarmupCosineSchedule(optimizer, num_epochs, warmup_steps)
    num_epochs_to_converge = 100
    grad_clip_norm = 1

    # Init tensorboard
    writer = SummaryWriter(run_directory)

    # # Add input images to tensorboard for sanity check
    fig = visualisation.sample_batch(dataloaders["train"], class_names)
    writer.add_figure('Input/train', fig)
    fig = visualisation.sample_batch(dataloaders["val"], class_names)
    writer.add_figure('Input/val', fig)

    # # Main training loop
    model, best_acc = train_model(model, dataloaders, optimizer, criterion, scheduler, num_epochs, device, dataset_sizes, len(class_names), writer, run_directory, warmup_steps, num_epochs_to_converge, grad_clip_norm)

    # Add sample inference outputs to tensorboard
    fig = visualisation.sample_batch(dataloaders["train"], class_names, model, device)
    writer.add_figure('Inference/train', fig)
    fig = visualisation.sample_batch(dataloaders["val"], class_names, model, device)
    writer.add_figure('Inference/val', fig)

    writer.close()

