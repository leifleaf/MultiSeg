#!usr/bin/env python

import argparse
import imgaug.augmenters as iaa

from train.davis2017_dataset import *
from train.datautils import splitd

commands = ['train', 'augs']

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cmd', choices=commands,
                        default=commands[0],
                        help='Display plots of the augmented masks used for training',
                        )
    parser.add_argument('-d', '--dataset', dest='dataset_path', type=str,
                        nargs=1,
                        default='G:\\Team Drives\\COML-Fall-2018\\T0-VidSeg\Data\\DAVIS',
                        )
    parser.add_argument('-o', '--optical-flow', dest='optical_flow_path', type=str,
                        nargs=1,
                        default='./opt_flow/models/pwcnet-lg-6-2-multisteps-chairsthingsmix/pwcnet.ckpt-595000')
    parser.add_argument('-v', '--validation-split', dest='val_split', type=float,
                        nargs=1, default=0.2)
    parser.add_argument('-p', '--print-debugs', dest='print_debugs', action='store_true')

    ############################################################################

    args = parser.parse_args()

    cmd = args.cmd
    dataset_path = args.dataset_path[0]
    optical_flow_path = args.optical_flow_path
    val_split = args.val_split
    print_debugs = args.print_debugs

    print('Arguments given to trainmaskrefine command: ')
    print(f'\tcommand\t{cmd}')
    print(f'\tdataset\t{dataset_path}')
    print(f'\toptical\t{optical_flow_path}')
    print(f'\tval split\t{val_split}')
    print(f'\tdebugs\t{print_debugs}')
    print()

    ############################################################################

    dataset = get_trainval(dataset_path)

    seq = iaa.Sequential([
        iaa.ElasticTransformation(alpha=(200, 1000), sigma=(20, 100)),
        iaa.GaussianBlur(sigma=(0.1, 7.5)),
        iaa.AdditiveGaussianNoise(scale=(1, 5))
    ])

    if args.cmd == 'augs':
        gen = dataset.paired_generator(seq)

        for X, y in gen:
            import matplotlib.pyplot as plt

            plt.imshow(X[..., 6].astype(int))
            plt.show()
            plt.imshow(y[..., 0])
            plt.show()
    elif args.cmd == 'train':
        from opt_flow.opt_flow import TensorFlowPWCNet
        from mask_refine.mask_refine import MaskRefineSubnet, MaskRefineModule

        train, val = splitd(dataset, 1 - val_split, val_split)
        train_gen, val_gen = train.paired_generator(seq), val.paired_generator(seq)

        pwc_net = TensorFlowPWCNet(model_pathname=optical_flow_path)
        mr_subnet = MaskRefineSubnet()
        mr_module = MaskRefineModule(pwc_net, mr_subnet)

        if args.print_debugs:
            print('Starting MaskRefine training...')

        hist = mr_module.train(train_gen, val_gen)
        if args.print_debugs:
            print(hist)

