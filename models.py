import tensorflow as tf
from object_detection.utils import config_util
from object_detection.builders import model_builder

from tensorflow.keras.applications import *
from tensorflow.keras import Sequential
from tensorflow.keras.layers import *

from globalVariables import DROPOUT_RATES, FC_LAYERS

MODELS_CLASSIFICATION = {
    # 'DenseNet121': DenseNet121,
    'InceptionV3': InceptionV3}
    # 'Xception': Xception}
    # 'VGG16': VGG16}
    # 'MobileNet': MobileNet,
    # 'MobileNetV2': MobileNetV2,
    # 'ResNet50': ResNet50,
    # 'ResNet50V2': ResNet50V2,
    # 'InceptionResNetV2': InceptionResNetV2,
    # 'DenseNet169': DenseNet169,
    # 'ResNet101': ResNet101,
    # 'ResNet101V2': ResNet101V2,
    # 'EfficientNetB0': EfficientNetB0,
    # 'EfficientNetB1': EfficientNetB1,
    # 'EfficientNetB2': EfficientNetB2}
    # 'EfficientNetB3': EfficientNetB3,
    # 'EfficientNetB4': EfficientNetB4,
    # 'EfficientNetB5': EfficientNetB5}


def userDefinedModel():
    """
    working function
    here you define any custom model

    returns
    -------
        model : object
            created model
    """

    model = Sequential([
        Conv2D(32, 3, activation='relu'),
        MaxPooling2D(),
        Conv2D(64, 3, activation='relu'),
        MaxPooling2D(),
        Flatten(),
        Dense(64, activation='relu'),
        Dense(1, activation='softmax')])

    return model


def unfreezeModel(model, num_input_layers, batch_norm, num_layers):
    """
    unfrezees a number of top layers of a model for training

    parameters
    ----------
        model : object
            model to be trained

        num_input_layers : int
            number of input layers in the model

        batch_norm : boolean
            whether a model has a batch normalization at the last layers or not

        num_layers : int
            number layers to unfreeze
        

    returns
    -------
        model : object
            model with unfreezed layers
    """

    num_last_layers = 3 + num_input_layers

    if batch_norm:

        num_last_layers += 1

    if FC_LAYERS != None:

        for layer in FC_LAYERS:

            if layer != None:

                num_last_layers += 1
        
        for layer in DROPOUT_RATES:

            if layer != None:

                num_last_layers += 1
        
    num_layers_unfreeze = num_layers + num_last_layers

    for layer in model.layers[-num_layers_unfreeze + 1: -num_last_layers]:
        if not isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = True

    return model


def buildClassificationPretrainedModel(model_path, pretrained_model, custom_objects, num_classes, activation, load_model):
    """
    either loads a model or takes a pretrained model as a parameter and recreates a new one
    without the last dense layer and defines a new head layer
    with the desired number of neurons

    parameters
    ----------
        model_path : string
            full path to the model

        pretrained_model : object


        custom_objects : dictionary
            contains custom objects from training that are were not loaded from tensorflow or keras libraries

            example:
            custom_objects = {
                'f1': f1,
                'categorical_focal_loss_fixed': categorical_focal_loss(alpha=[[.25, .25]], gamma=2)}

        num_classes : int
            number of the last dense layer neurons

        activation : object
            activation function at the last layer

        load_model : boolean
            whether to load an existing model from path

    returns
    -------
        model : object
            recreated model
    """

    if load_model:
        pretrained_model = tf.keras.models.load_model(model_path, custom_objects)

    model = tf.keras.models.Sequential()
    # add all layers except last layer
    for layer in pretrained_model.layers[:-1]:
        model.add(layer)

    # add last classification layer
    model.add(tf.keras.layers.Dense(num_classes, activation=activation))

    return model


def buildClassificationImageNetModel(
    inputs, 
    model_name, model_imagenet, 
    pooling, dropout_connect_rate, do_batch_norm, initial_dropout, 
    concat_features_before, concat_features_after, 
    fc_layers, dropout_rates, 
    num_classes, activation, 
    do_predictions):
    """
    builds classification ImageNet model body and creates custom head layers after global pooling
    the process of building a model architecture is as follows:
        1. an ImageNet model body is initialized without head layers, that is all layers before global pooling (included)
        2. optional batch normalization and dropout layers are added
        3. if additional feature layers are needed:
            - it either concatenates them now with a global pooling layer, or a batch normalization layer, or a dropout layer 
            (depends on the last layer in the model architecture)
            - otherwise additional features are concatenated with the last layer before the dense (prediction) layer
        4. optional fully connected and dropout layers are addded
        5. optional prediction layer is added
        6. finally, the model is created and returned

    parameters
    ----------

        inputs : list
            list of input layers

        model_name : string
            name of the ImageNet model

        model_imagenet : tf.keras.applications object
            ImageNet model to load

        pooling : string or None
            either 'avg', 'max', or None
            None means that the output of the model will be the 4D tensor output of the last convolutional layer.
            'avg' means that global average pooling will be applied to the output of the last convolutional layer, and thus the output of the model will be a 2D tensor
            'max' means that global max pooling will be applied.

        dropout_connect_rate : decimal
            works only with EfficientNet models
            defines rate of all dropout layers before global pooling

        do_batch_norm : boolean
            whether to include batch normalization layer after global pooling

        initial_dropout : decimal
            dropout rate after global pooling

        concat_features_before : boolean
            whether to concatenate additional features before fully connected and dropout layers

        concat_features_after : boolean
            whether to concatenate additional features after fully connected and dropout layers and before prediction layer

        fc_layers : tuple or None
            whether to include additional fully connected layers before prediction layer

        dropout_rates : tuple or None
            whether to include dropout layers between last fully connected layers and their rate

        num_classes : int
            number of classes

        activation : object
            activation function of the last dense layer

        do_predictions : boolean
            whether to create last dense layer

    returns
    -------
        model : object
            created model
    """

    if 'EfficientNet' in model_name:

        imagenet_model = model_imagenet(
            include_top=False, weights='imagenet', input_tensor=inputs[0], drop_connect_rate=dropout_connect_rate, pooling=pooling)
    else:

        imagenet_model = model_imagenet(
            include_top=False, weights='imagenet', input_tensor=inputs[0], pooling=pooling)

    imagenet_model.trainable = False

    feature_extractor = imagenet_model.output

    if do_batch_norm:

        feature_extractor = tf.keras.layers.BatchNormalization()(feature_extractor)

    if initial_dropout is not None:

        feature_extractor = tf.keras.layers.Dropout(initial_dropout)(feature_extractor)
    
    if concat_features_before:

        feature_layers = [layer for layer in inputs[1:]]
        feature_layers.insert(0, feature_extractor)

        concat_layer = tf.keras.layers.Concatenate(name='concat_features')(feature_layers)
    
    else:

        concat_layer = None

    if (fc_layers is not None) or (dropout_rates is not None):

        for fc, dropout in zip(fc_layers, dropout_rates):

            if fc == None:

                continue

            else:

                if concat_layer is not None:

                    feature_extractor = tf.keras.layers.Dense(fc, activation='relu')(concat_layer)

                    concat_layer = None

                else:

                    feature_extractor = tf.keras.layers.Dense(fc, activation='relu')(feature_extractor)

            if dropout == None:

                continue

            else:

                feature_extractor = tf.keras.layers.Dropout(dropout)(feature_extractor)

    if concat_features_after:

        feature_layers = [layer for layer in inputs[1:]]
        feature_layers.insert(0, feature_extractor)

        concat_layer = tf.keras.layers.Concatenate(name='concat_features')(feature_layers)
    
    else:

        concat_layer = None

    if do_predictions:

        if concat_layer is not None:

            predictions = tf.keras.layers.Dense(num_classes, activation=activation)(concat_layer)

        else:

            predictions = tf.keras.layers.Dense(num_classes, activation=activation)(feature_extractor)

        model = tf.keras.Model(inputs=inputs, outputs=predictions)

        return model

    else:

        if concat_layer is not None:

            model = tf.keras.Model(inputs=inputs, outputs=concat_layer)

        else:

            model = tf.keras.Model(inputs=inputs, outputs=feature_extractor)

        return model


def buildDetectionModel(num_classes, checkpoint_path, config_path, dummy_shape):
    """
    builds an object localization/classification model from Object Detection API library and loads weights

    to download a checkpoint, use following commands in the terminal:
        - wget http://download.tensorflow.org/models/object_detection/tf2/20200711/efficientdet_d4_coco17_tpu-32.tar.gz -O ./efficientdet_d4_1024x1024.tar.gz (use proper link and filename)
        - tar -xf efficientdet_d4_1024x1024.tar.gz
        - mv efficientdet_d4_coco17_tpu-32/checkpoint models/research/object_detection/test_data/

    parameters
    ----------

        num_classes : int
            number of neurons at the last dense layer

        checkpoint_path : string
            path to the model training checkpoint to load

        config_path : string
            path to the model configuration file to load

        dummy_shape : tuple
            used to define a dummy image with specified shape and run it through the model so that variables are created

    returns
    -------
        detection_model : object
            restored model
    """

    # Download the checkpoint and put it into models/research/object_detection/test_data/
    # wget http://download.tensorflow.org/models/object_detection/tf2/20200711/efficientdet_d4_coco17_tpu-32.tar.gz -O ./efficientdet_d4_1024x1024.tar.gz
    # tar -xf efficientdet_d4_1024x1024.tar.gz
    # mv efficientdet_d4_coco17_tpu-32/checkpoint models/research/object_detection/test_data/

    configs = config_util.get_configs_from_pipeline_file(
        config_path, config_override=None)

    model_config = configs['model']

    model_config.ssd.num_classes = num_classes

    model_config.ssd.freeze_batchnorm = True

    detection_model = model_builder.build(
        model_config=model_config, is_training=True)

    tmp_box_predictor_checkpoint = tf.train.Checkpoint(
        _base_tower_layers_for_heads=detection_model._box_predictor._base_tower_layers_for_heads, _box_prediction_head=detection_model._box_predictor._box_prediction_head)

    tmp_model_checkpoint = tf.train.Checkpoint(
        _feature_extractor=detection_model._feature_extractor, _box_predictor=tmp_box_predictor_checkpoint)

    checkpoint = tf.train.Checkpoint(model=tmp_model_checkpoint)

    checkpoint.restore(checkpoint_path)

    dummy = tf.zeros(shape=dummy_shape)
    tmp_image, tmp_shapes = detection_model.preprocess(dummy)

    tmp_prediction_dict = detection_model.predict(tmp_image, tmp_shapes)

    tmp_detections = detection_model.postprocess(
        tmp_prediction_dict, tmp_shapes)

    tf.keras.backend.set_learning_phase(True)

    return detection_model


def buildDenoisingAutoencoder(
    c_inputs, 
    c_model_name, c_model_imagenet, 
    c_pooling, c_dropout_connect_rate, c_do_batch_norm, c_initial_dropout, 
    c_concat_features_before, c_concat_features_after, 
    c_fc_layers, c_dropout_rates, 
    c_num_classes, c_activation, 
    c_do_predictions,
    inputs_features,
    dense_neurons_data_features, dense_neurons_encoder, dense_neurons_bottle, dense_neurons_decoder,
    predictions_features,
    input_den_autoenc_layers):

    classification_model = buildClassificationImageNetModel(
        c_inputs, c_model_name, c_model_imagenet,
        c_pooling, c_dropout_connect_rate, c_do_batch_norm, c_initial_dropout,
        c_concat_features_before, c_concat_features_after, 
        c_fc_layers, c_dropout_rates,
        c_num_classes, c_activation, 
        c_do_predictions)

    dense_data_features_layer = tf.keras.layers.Dense(dense_neurons_data_features, activation='relu', name="dense_data_features_layer", use_bias=False)(classification_model.layers[-1].output)
    concat_features_layers = [dense_data_features_layer]
    for features_layer in inputs_features:
        concat_features_layers.append(features_layer)

    concat_layer = tf.keras.layers.Concatenate(name='concat_features')(concat_features_layers)
    
    dense_encoder_layer = tf.keras.layers.Dense(dense_neurons_encoder, activation='relu', name="dense_encoder_layer", use_bias=False)(concat_layer)
    dense_bottle_layer = tf.keras.layers.Dense(dense_neurons_bottle, activation='relu', name="dense_bottle_layer", use_bias=False)(dense_encoder_layer)
    dense_decoder_layer = tf.keras.layers.Dense(dense_neurons_decoder, activation='relu', name="dense_decoder_layer", use_bias=False)(dense_bottle_layer)

    prediction_layers = []

    for idx, (features, activation) in enumerate(predictions_features):

        prediction_layer = tf.keras.layers.Dense(features, activation=activation, name=('prediction_layer_' + idx))(dense_decoder_layer)

        prediction_layers.append(prediction_layer)

    denoising_autoencoder = tf.keras.models.Model(inputs=input_den_autoenc_layers, outputs=prediction_layers)

    return denoising_autoencoder
