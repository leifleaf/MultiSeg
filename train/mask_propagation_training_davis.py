#!usr/bin/env python

from keras.backend import tf
import numpy as np
from skimage import io

# static GPU memory allocation for tensorflow (reserve some GPU for PyTorch optical flow)
gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.75)
sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options))

# Our own modules
from train.davis2016_dataset import MaskPropDavisDataset
from opt_flow.pwc_net_wrapper import PWCNetWrapper
from mask_refine.mask_propagation import *

##########################################################################
#
# Load Dataset Wrapper, Optical Flow Model, and UNet
#
##########################################################################

dataset = MaskPropDavisDataset("./mask_prop/DAVIS", "480p", val_videos=[
    "car-shadow", "breakdance", "camel", "scooter-black", "libby", "drift-straight"
])
optical_flow = PWCNetWrapper("./opt_flow/pwc_net.pth.tar")
model = MaskPropagation()

##########################################################################
#
# Optical Flow
#
##########################################################################


# TODO move these functions into either davis_data or elsewhere
def get_model_input(img_prev_p, img_curr_p, mask_prev_p, mask_curr_p, report_errors=False):
    """
    Returns tensor that contains previous mask and optical flow, and also
    returns current mask as the ground truth value.
    """
    img_prev, img_curr = pad_image(io.imread(img_prev_p)), pad_image(io.imread(img_curr_p))

    # Check 1
    if img_prev.shape != img_curr.shape:
        if report_errors: print("ERROR: img_prev.shape != img_curr.shape", img_prev_p, img_prev.shape, img_curr.shape)
        return None, None
    if img_prev.shape != (480, 864, 3):
        if report_errors: print("ERROR: img_prev.shape != (480, 864, 3)", img_prev_p, img_prev.shape)
        return None, None

    finalflow = optical_flow.infer_flow_field(img_prev, img_curr)
    finalflow_x, finalflow_y = finalflow[:, :, 0], finalflow[:, :, 1]
    finalflow[:, :, 0] = (finalflow_x - finalflow_x.mean()) / finalflow_x.std()
    finalflow[:, :, 1] = (finalflow_y - finalflow_y.mean()) / finalflow_y.std()

    # Check 2
    if finalflow.shape != (480, 864, 2):
        if report_errors: print("ERROR: finalflow.shape != (480, 864, 2)", img_prev_p, finalflow.shape)
        return None, None

    mask_prev = pad_image(io.imread(mask_prev_p)) / 255
    mask_curr = pad_image(io.imread(mask_curr_p)) / 255

    # Check 3
    if mask_prev.shape != mask_curr.shape:
        if report_errors: print("ERROR: mask_prev.shape != mask_curr.shape", img_prev_p, mask_prev.shape, mask_curr.shape)
        return None, None
    if mask_prev.shape != (480, 864):
        if report_errors: print("ERROR: mask_prev.shape != (480, 864)", img_prev_p, mask_prev.shape)
        return None, None

    model_input = np.stack([mask_prev, finalflow[:, :, 0], finalflow[:, :, 1]], axis=2)

    return model_input, mask_curr


##########################################################################
#
# Define Data Generators
#
##########################################################################

def create_data_generators(batch_size=4):
    train, val = dataset.get_train_val()

    print("train size: ", len(train))
    print("val size: ", len(val))

    train_generator = dataset.data_generator(train, get_model_input, batch_size=batch_size)
    val_generator = dataset.data_generator(val, get_model_input, batch_size=batch_size)

    return train_generator, val_generator


train_generator, val_generator = create_data_generators()

##########################################################################
#
# Train Model
#
##########################################################################

model.train(train_generator, val_generator)
