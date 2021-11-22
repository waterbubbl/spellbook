from globalVariables import (
    BATCH_SIZES, NUM_EPOCHS, START_EPOCH, NUM_CLASSES, IMAGE_SHAPE,
    DATA_FILEPATHS, TRAIN_FILEPATHS, VAL_FILEPATHS, DO_KFOLD, NUM_FOLDS, RANDOM_STATE, MAX_FILEPARTS_TRAIN, MAX_FILEPARTS_VAL,
    METADATA, ID_COLUMN, FEATURE_COLUMN, FULL_RECORD,
    SHUFFLE_BUFFER_SIZE ,PERMUTATIONS_CLASSIFICATION, DO_PERMUTATIONS,
    NUM_FEATURES, FC_LAYERS, INITIAL_DROPOUT, DROPOUT_RATES, DROP_CONNECT_RATE, AUTOENCODER_FC, IMAGE_FEATURE_EXTRACTOR_FC, OUTPUT_ACTIVATION, MODEL_POOLING, UNFREEZE, NUM_UNFREEZE_LAYERS,
    LEARNING_RATE, LR_DECAY_STEPS, LR_DECAY_RATE, LR_LADDER, LR_LADDER_STEP, LR_LADDER_EPOCHS, LR_EXP, FROM_LOGITS, LABEL_SMOOTING,
    SAVE_TRAIN_WEIGHTS_DIR, SAVE_TRAIN_INFO_DIR, LOAD_WEIGHTS, CLASSIFICATION_CHECKPOINT_PATH)

from models import MODELS_CLASSIFICATION, unfreezeModel, userDefinedModel, buildAutoencoderPetfinder, buildClassificationImageNetModel, buildClassificationPretrainedModel
from train import classificationCustomTrain
from preprocessFunctions import minMaxNormalizeNumpy
from losses import rootMeanSquaredErrorLoss
from helpers import getFullPaths

import time
import numpy as np
import tensorflow as tf
import tensorflow.keras.backend as K
from sklearn.model_selection import KFold

gpus = tf.config.experimental.list_physical_devices('GPU')
for gpu in gpus:
    tf.config.experimental.set_memory_growth(gpu, True)

strategy = tf.distribute.MirroredStrategy(
    devices=["GPU:0", "GPU:1"], cross_device_ops=tf.distribute.HierarchicalCopyAllReduce())


def сlassificationСustom():
    """
    XXX
    """

    data_paths_list = np.array(getFullPaths(DATA_FILEPATHS))

    for model_name, model_imagenet in MODELS_CLASSIFICATION.items():

        batch_size_per_replica = BATCH_SIZES[model_name]
        batch_size = batch_size_per_replica * strategy.num_replicas_in_sync

        if DO_KFOLD:

            kfold = KFold(NUM_FOLDS, shuffle=True, random_state=RANDOM_STATE)

            for fold, (train_ix, val_ix) in enumerate(kfold.split(data_paths_list)):

                train_paths_list = np.ndarray.tolist(data_paths_list[train_ix])
                val_paths_list = np.ndarray.tolist(data_paths_list[val_ix])

                with strategy.scope():


                    # if ((model_name == 'Xception') and (fold < 3)):
                    #     continue

                    # if ((model_name == 'Xception') and (fold == 3)):

                    #     LOAD_WEIGHTS = True

                    #     START_EPOCH = 31
                    #     LEARNING_RATE = 0.000125

                    # else:

                    #     LOAD_WEIGHTS = False
                    #     START_EPOCH = 0
                    #     LEARNING_RATE = 0.001

                    # create model, loss, optimizer and metrics instances here
                    # reset model, optimizer (AND learning rate), loss and metrics after each iteration

                    # classification_model = userDefinedModel(NUM_CLASSES, OUTPUT_ACTIVATION)

                    input_image_layer = tf.keras.layers.Input(shape=(IMAGE_SHAPE[0], IMAGE_SHAPE[1], IMAGE_SHAPE[2], ), name='input_image')

                    classification_model = buildClassificationImageNetModel(
                        input_image_layer, model_name, model_imagenet,
                        MODEL_POOLING, DROP_CONNECT_RATE, INITIAL_DROPOUT, FC_LAYERS, DROPOUT_RATES,
                        NUM_CLASSES, OUTPUT_ACTIVATION, trainable=False, do_predictions=True)

                    if UNFREEZE:
                        num_layers = 0
                        for layer in classification_model.layers:
                            num_layers += 1
                        to_unfreeze = num_layers // 10

                        classification_model = unfreezeModel(classification_model, to_unfreeze)

                    if LOAD_WEIGHTS:
                        classification_model.load_weights(CLASSIFICATION_CHECKPOINT_PATH)

                    # autoencoder = buildAutoencoderPetfinder(
                    #     imageFeatureExtractor.output.shape[1], NUM_FEATURES, IMAGE_FEATURE_EXTRACTOR_FC, AUTOENCODER_FC)

                    # concat_layer = tf.keras.layers.Concatenate(name='concat_features_dense')([autoencoder.layers[-4].output, autoencoder.layers[-3].output, autoencoder.layers[-2].output, autoencoder.layers[1].output])
                    # dense_1 = tf.keras.layers.Dense(256, activation='relu')(concat_layer)
                    # dropout_1 = tf.keras.layers.Dropout(0.5)(dense_1)
                    # dense_2 = tf.keras.layers.Dense(64, activation='relu')(dropout_1)
                    # predictions = tf.keras.layers.Dense(NUM_CLASSES, name='predictions')(dense_2)

                    # autoencoder_classification = tf.keras.models.Model(inputs=[autoencoder.layers[0].output, autoencoder.layers[2].output], outputs=predictions)

                    loss_object = tf.losses.CategoricalCrossentropy(
                        from_logits=FROM_LOGITS, label_smoothing=LABEL_SMOOTING, reduction=tf.keras.losses.Reduction.NONE)

                    # loss_object = tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.NONE)

                    def compute_total_loss(labels, predictions):
                        per_gpu_loss = loss_object(labels, predictions)
                        return tf.nn.compute_average_loss(
                            per_gpu_loss, global_batch_size=batch_size)

                    val_loss = tf.keras.metrics.Mean(name='val_loss')

                    if LR_EXP:
                        exp_learning_rate = tf.keras.optimizers.schedules.ExponentialDecay(
                            initial_learning_rate=LEARNING_RATE, decay_steps=LR_DECAY_STEPS, decay_rate=LR_DECAY_RATE)
                        optimizer = tf.keras.optimizers.Adam(learning_rate=exp_learning_rate)

                    else:
                        optimizer = tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE)

                    train_accuracy = tf.keras.metrics.CategoricalAccuracy(
                        name='train_accuracy')
                    val_accuracy = tf.keras.metrics.CategoricalAccuracy(
                        name='val_accuracy')

                    # train_accuracy = tf.keras.metrics.RootMeanSquaredError(
                    #     name='train_RMSE')
                    # val_accuracy = tf.keras.metrics.RootMeanSquaredError(
                    #     name='val_RMSE')

                    # rename optimizer weights to train multiple models
                    with K.name_scope(optimizer.__class__.__name__):
                        for i, var in enumerate(optimizer.weights):
                            name = 'variable{}'.format(i)
                            optimizer.weights[i] = tf.Variable(
                                var, name=name)

                classificationCustomTrain(
                    batch_size, NUM_EPOCHS, START_EPOCH,
                    train_paths_list, val_paths_list, fold, MAX_FILEPARTS_TRAIN, MAX_FILEPARTS_VAL,
                    METADATA, ID_COLUMN, FEATURE_COLUMN, FULL_RECORD,
                    SHUFFLE_BUFFER_SIZE, PERMUTATIONS_CLASSIFICATION, DO_PERMUTATIONS, minMaxNormalizeNumpy,
                    model_name, classification_model,
                    loss_object, val_loss, compute_total_loss,
                    LR_LADDER, LR_LADDER_STEP, LR_LADDER_EPOCHS, optimizer,
                    train_accuracy, val_accuracy,
                    SAVE_TRAIN_INFO_DIR, SAVE_TRAIN_WEIGHTS_DIR,
                    strategy,
                    is_autoencoder=False, pretrained=False)

                print('________________________________________')
                print('\n')
                print('TRAINING FINISHED FOR ' + model_name + ', fold ' + str(fold + 1) + '/' + str(NUM_FOLDS) + ' !')
                print('\n')
                print('________________________________________')

                del train_paths_list
                del val_paths_list
                del classification_model
                del loss_object
                del val_loss
                del optimizer
                del train_accuracy
                del val_accuracy

                K.clear_session()

                # sleep 120 seconds
                print('Sleeping 120 seconds after training ' + model_name + ', fold ' + str(fold + 1) + '/' + str(NUM_FOLDS) + '. Zzz...')
                time.sleep(120)

        else:

            train_paths_list = getFullPaths(TRAIN_FILEPATHS)
            val_paths_list = getFullPaths(VAL_FILEPATHS)

            with strategy.scope():

                # create model, loss, optimizer and metrics instances here
                # reset model, optimizer (AND learning rate), loss and metrics after each iteration

                # classification_model = userDefinedModel(NUM_CLASSES, OUTPUT_ACTIVATION)

                input_image_layer = tf.keras.layers.Input(shape=(IMAGE_SHAPE[0], IMAGE_SHAPE[1], IMAGE_SHAPE[2], ), name='input_image')

                classification_model = buildClassificationImageNetModel(
                    input_image_layer, model_name, model_imagenet,
                    MODEL_POOLING, DROP_CONNECT_RATE, INITIAL_DROPOUT, FC_LAYERS, DROPOUT_RATES,
                    NUM_CLASSES, OUTPUT_ACTIVATION, trainable=False, do_predictions=True)

                if UNFREEZE:
                    num_layers = 0
                    for layer in classification_model.layers:
                        num_layers += 1
                    to_unfreeze = num_layers // 10

                    classification_model = unfreezeModel(classification_model, to_unfreeze)

                if LOAD_WEIGHTS:
                    classification_model.load_weights(CLASSIFICATION_CHECKPOINT_PATH)

                # autoencoder = buildAutoencoderPetfinder(
                #     imageFeatureExtractor.output.shape[1], NUM_FEATURES, IMAGE_FEATURE_EXTRACTOR_FC, AUTOENCODER_FC)

                # concat_layer = tf.keras.layers.Concatenate(name='concat_features_dense')([autoencoder.layers[-4].output, autoencoder.layers[-3].output, autoencoder.layers[-2].output, autoencoder.layers[1].output])
                # dense_1 = tf.keras.layers.Dense(256, activation='relu')(concat_layer)
                # dropout_1 = tf.keras.layers.Dropout(0.5)(dense_1)
                # dense_2 = tf.keras.layers.Dense(64, activation='relu')(dropout_1)
                # predictions = tf.keras.layers.Dense(NUM_CLASSES, name='predictions')(dense_2)

                # autoencoder_classification = tf.keras.models.Model(inputs=[autoencoder.layers[0].output, autoencoder.layers[2].output], outputs=predictions)

                loss_object = tf.losses.BinaryCrossentropy(
                    from_logits=FROM_LOGITS, reduction=tf.keras.losses.Reduction.NONE)

                # loss_object = tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.NONE)

                def compute_total_loss(labels, predictions):
                    per_gpu_loss = loss_object(labels, predictions)
                    return tf.nn.compute_average_loss(
                        per_gpu_loss, global_batch_size=batch_size)

                val_loss = tf.keras.metrics.Mean(name='val_loss')

                if LR_EXP:
                    exp_learning_rate = tf.keras.optimizers.schedules.ExponentialDecay(
                        initial_learning_rate=LEARNING_RATE, decay_steps=LR_DECAY_STEPS, decay_rate=LR_DECAY_RATE)
                    optimizer = tf.keras.optimizers.Adam(learning_rate=exp_learning_rate)

                else:
                    optimizer = tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE)

                train_accuracy = tf.keras.metrics.BinaryAccuracy(
                    name='train_accuracy')
                val_accuracy = tf.keras.metrics.BinaryAccuracy(
                    name='val_accuracy')

                # train_accuracy = tf.keras.metrics.RootMeanSquaredError(
                #     name='train_RMSE')
                # val_accuracy = tf.keras.metrics.RootMeanSquaredError(
                #     name='val_RMSE')

                # rename optimizer weights to train multiple models
                with K.name_scope(optimizer.__class__.__name__):
                    for i, var in enumerate(optimizer.weights):
                        name = 'variable{}'.format(i)
                        optimizer.weights[i] = tf.Variable(
                            var, name=name)

            classificationCustomTrain(
                batch_size, NUM_EPOCHS, START_EPOCH,
                train_paths_list, val_paths_list, None, MAX_FILEPARTS_TRAIN, MAX_FILEPARTS_VAL,
                METADATA, ID_COLUMN, FEATURE_COLUMN, FULL_RECORD,
                SHUFFLE_BUFFER_SIZE, PERMUTATIONS_CLASSIFICATION, DO_PERMUTATIONS, minMaxNormalizeNumpy,
                model_name, classification_model,
                loss_object, val_loss, compute_total_loss,
                LR_LADDER, LR_LADDER_STEP, LR_LADDER_EPOCHS, optimizer,
                train_accuracy, val_accuracy,
                SAVE_TRAIN_INFO_DIR, SAVE_TRAIN_WEIGHTS_DIR,
                strategy,
                is_autoencoder=False, pretrained=False)

            print('________________________________________')
            print('\n')
            print('TRAINING FINISHED FOR ' + model_name + '!')
            print('\n')
            print('________________________________________')

            del train_paths_list
            del val_paths_list
            del classification_model
            del loss_object
            del val_loss
            del optimizer
            del train_accuracy
            del val_accuracy

            K.clear_session()

            # sleep 300 seconds
            print('Sleeping 300 seconds after training ' + model_name + '. Zzz...')
            time.sleep(300)

        del batch_size_per_replica
        del batch_size
