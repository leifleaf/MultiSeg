from datetime import datetime
from keras.callbacks import TensorBoard, CSVLogger, ModelCheckpoint
from keras.layers import Input, Conv2D, Dropout, MaxPooling2D, Conv2DTranspose, Concatenate
from keras.models import Model
from keras.optimizers import Adam
import numpy as np

from opt_flow.pwc_net_wrapper import PWCNetWrapper

__all__ = ['MaskRefineSubnet', 'MaskRefineModule']


def _conv2d(filters, kernel=3, activation='relu', kernel_initializer='he_normal', name=None):
    return Conv2D(filters, kernel, activation=activation, padding='same',
                  kernel_initializer=kernel_initializer, name=name)


def _deconv2d(filters, activation=None, name=None):
    return Conv2DTranspose(filters, (2, 2), strides=(2, 2),
                           activation=activation, name=name)


def _maxpool2d(pool_size=(2, 2)):
    return MaxPooling2D(pool_size=pool_size)


def _concat(axis=3):
    return Concatenate(axis=axis)


class MaskRefineSubnet:
    """
    Model for just the U-Net architecture within the Mask Refine Module. (Namely,
    this subnet does not handle running the optical flow network.)
    """

    def __init__(self, weights_path=None):
        self._build_model()

        if weights_path is not None:
            self.load_weights(weights_path)

    def _build_model(self, optimizer=Adam(lr=1e-4), loss='binary_crossentropy'):
        """
        Builds the U-Net for the mask propagation network, 5 levels deep.
        :param optimizer: optimizer object to use to train
        :param loss: loss function (as string) to use to train

        Adapted by Shivam, Derek, and Tim from https://github.com/ShawDa/unet-rgb/blob/master/unet.py. Adaptations
        include a binary focal loss, transposed convolutions, and varied activations.
        """
        inputs = Input((None, None, 6))

        # block 1 (down-1)
        conv1 = _conv2d(64)(inputs)
        conv1 = _conv2d(64)(conv1)
        pool1 = _maxpool2d()(conv1)

        # block 2 (down-2)
        conv2 = _conv2d(128)(pool1)
        conv2 = _conv2d(128)(conv2)
        pool2 = _maxpool2d()(conv2)

        # block 3 (down-3)
        conv3 = _conv2d(256)(pool2)
        conv3 = _conv2d(256)(conv3)
        pool3 = _maxpool2d()(conv3)

        # block 4 (down-4)
        conv4 = _conv2d(512)(pool3)
        conv4 = _conv2d(512)(conv4)
        drop4 = Dropout(0.5)(conv4)
        pool4 = _maxpool2d()(drop4)

        # block 5 (5)
        conv5 = _conv2d(1024)(pool4)
        conv5 = _conv2d(1024)(conv5)
        drop5 = Dropout(0.5)(conv5)

        # block 6 (up-4)
        up6 = _deconv2d(1024)(drop5)

        merge6 = _concat()([drop4, up6])
        conv6 = _conv2d(512)(merge6)
        conv6 = _conv2d(512)(conv6)

        # block 7 (up-3)
        up7 = _deconv2d(512)(conv6)
        merge7 = _concat()([conv3, up7])
        conv7 = _conv2d(256)(merge7)
        conv7 = _conv2d(256)(conv7)

        # block 8 (up-2)
        up8 = _deconv2d(256)(conv7)
        merge8 = _concat()([conv2, up8])
        conv8 = _conv2d(128)(merge8)
        conv8 = _conv2d(128)(conv8)

        # block 9 (up-1)
        up9 = _deconv2d(128)(conv8)
        merge9 = _concat()([conv1, up9])
        conv9 = _conv2d(64)(merge9)
        conv9 = _conv2d(64)(conv9)
        conv9 = _conv2d(2)(conv9)

        # block 10 (final outputs)
        conv10 = _conv2d(1, kernel=1, activation='sigmoid')(conv9)

        model = Model(inputs=[inputs], outputs=[conv10])

        # compile model
        metrics = ['binary_accuracy', 'binary_crossentropy']
        model.compile(optimizer=optimizer, loss=loss, metrics=metrics)

        self._model = model

    def load_weights(self, weights_path):
        """Load pretrained weights."""

        self._model.load_weights(weights_path)

    def train(self, train_generator, val_generator, epochs=30, steps_per_epoch=500, val_steps_per_epoch=100):
        history_file = "logs/mask_refine_history_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".csv"

        callbacks = [
            TensorBoard(
                log_dir="logs",
                histogram_freq=0,
                write_graph=True,
                write_images=False
            ),
            ModelCheckpoint(
                "logs/davis_unet_weights__{epoch:02d}__{val_loss:.2f}.h5",
                verbose=0, save_weights_only=True
            ),
            CSVLogger(history_file)
        ]

        history = self._model.fit_generator(
            train_generator,
            steps_per_epoch=steps_per_epoch,
            validation_data=val_generator,
            validation_steps=val_steps_per_epoch,
            epochs=epochs,
            callbacks=callbacks
        )

        return history

    def predict(self, input_stack):
        """Run inference for a set of inputs.
        :param input_stack: current image, mask, optical flow of shape [h, w, 6]
        :return: refined mask of shape [h, w, 1]

        input stack (concatenated along the 3rd axis (axis=2)):
        IMAGE [h,w,3]
        MASK  [h,w,1]
        FLOW  [h,w,2]
        """

        return self._model.predict(input_stack, batch_size=input_stack.shape[0])

    @staticmethod
    def build_input_stack(image, mask, flow_field):
        return np.concatenate((image, mask, flow_field), axis=2)

    def __call__(self, *args):
        return self._model(*args)


class MaskRefineModule:
    """
    Model for the entire Mask Refine network: we don't handle the creation of
    the subnetworks here, just assembly and pipelining.
    """

    def __init__(self, optical_flow_model: PWCNetWrapper, mask_refine_subnet: MaskRefineSubnet):
        self.optical_flow_model = optical_flow_model
        self.mask_refine_subnet = mask_refine_subnet

        self._build_model()

    def _build_model(self):

        # TODO finish

        # model = Model(inputs=[], outputs=[])

        pass

    def refine_mask(self, input_stack):
        """
        Refines a coarse probability mask generated by the ImageSeg module into
        :param input_stack: previous image, current image, coarse_mask of shape [h, w, 7]
        :return: refined mask of shape [h, w, 1]

        input stack (concatenated along the 3rd axis (axis=2)):
        PREV IMAGE  [h, w, 3]
        CURR IMAGE  [h, w, 3]
        COARSE MASK [h, w, 1]
        """

        flow_field = self.optical_flow_model.infer_flow_field(input_stack[..., 0:3], input_stack[..., 3:6])

        subnet_input_stack = np.concatenate((input_stack[..., 3:6],), axis=2)

        self.mask_refine_subnet.predict()

        pass

    @staticmethod
    def build_input_stack(prev_image, curr_image, coarse_mask):
        return np.concatenate((prev_image, curr_image, coarse_mask), axis=2)