import glob
import os
import sys
import random
import time
import numpy as np
import cv2
import math

import tensorflow as tf
import carla


try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass


SHOW_PREVIEW = False
IM_WIDTH = 640
IM_HEIGHT = 480
SECONDS_PER_EPISODE = 1000
REPLAY_MEMORY_SIZE = 5_000
MIN_REPLAY_MEMORY_SIZE = 1_000
PREDICTION_BATCH_SIZE = 1
MINIBATCH_SIZE = 16
TRAINING_BATCH_SIZE = MINIBATCH_SIZE // 4
UPDATE_TARGET_EVERY = 5
THROTTLE = 0.25
MULTIPLIER = 0.25

MEMORY_FRACTION = 0.8
MIN_REWARD = -200

EPISODES = 100

DISCOUNT = 0.99
epsilon = 1
EPSILON_DECAY = 0.95 ## 0.9975 99975
MIN_EPSILON = 0.001

AGGREGATE_STATS_EVERY = 10


class CarEnv:
    SHOW_CAM = SHOW_PREVIEW
    STEER_AMT = 1.0
    im_width = IM_WIDTH
    im_height = IM_HEIGHT
    front_camera = None

    def __init__(self):
        self.client = carla.Client("127.0.0.1", 2000)
        self.client.set_timeout(2.0)
        self.world = self.client.get_world()
        self.blueprint_library = self.world.get_blueprint_library()
        self.model_3 = self.blueprint_library.filter("model3")[0]

    def reset(self):
        self.collision_hist = []
        self.actor_list = []

        self.transform = random.choice(self.world.get_map().get_spawn_points())
        self.vehicle = self.world.spawn_actor(self.model_3, self.transform)
        self.actor_list.append(self.vehicle)

        self.rgb_cam = self.blueprint_library.find('sensor.camera.rgb')
        self.rgb_cam.set_attribute("image_size_x", f"{self.im_width}")
        self.rgb_cam.set_attribute("image_size_y", f"{self.im_height}")
        self.rgb_cam.set_attribute("fov", f"110")

        transform = carla.Transform(carla.Location(x=2.5, z=0.7))
        self.sensor = self.world.spawn_actor(self.rgb_cam, transform, attach_to=self.vehicle)
        self.actor_list.append(self.sensor)
        self.sensor.listen(lambda data: self.process_img(data))

        self.vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=0.0))
        time.sleep(4)

        colsensor = self.blueprint_library.find("sensor.other.collision")
        self.colsensor = self.world.spawn_actor(colsensor, transform, attach_to=self.vehicle)
        self.actor_list.append(self.colsensor)
        self.colsensor.listen(lambda event: self.collision_data(event))

        while self.front_camera is None:
            time.sleep(0.01)

        self.episode_start = time.time()
        self.vehicle.apply_control(carla.VehicleControl(throttle=0.0, brake=0.0))

        return self.front_camera

    def collision_data(self, event):
        self.collision_hist.append(event)

    def process_img(self, image):
        i = np.array(image.raw_data)
        #print(i.shape)
        i2 = i.reshape((self.im_height, self.im_width, 4))
        i3 = i2[:, :, :3]
        if self.SHOW_CAM:
            cv2.imshow("", i3)
            cv2.waitKey(1)
        self.front_camera = i3

    def step(self, action):
        if action == 0:
            self.vehicle.apply_control(carla.VehicleControl(throttle=THROTTLE, steer=-MULTIPLIER*self.STEER_AMT))
        elif action == 1:
            self.vehicle.apply_control(carla.VehicleControl(throttle=THROTTLE, steer= 0))
        elif action == 2:
            self.vehicle.apply_control(carla.VehicleControl(throttle=THROTTLE, steer=MULTIPLIER*self.STEER_AMT))

        v = self.vehicle.get_velocity()
        kmh = int(3.6 * math.sqrt(v.x**2 + v.y**2 + v.z**2))

        if len(self.collision_hist) != 0:
            done = True
        elif kmh < 50:
            done = False
        else:
            done = False

        if self.episode_start + SECONDS_PER_EPISODE < time.time():
            done = True

        return self.front_camera, done, None

# # Own Tensorboard class
# class ModifiedTensorBoard(TensorBoard):

    # # Overriding init to set initial step and writer (we want one log file for all .fit() calls)
    # def __init__(self, **kwargs):
        # super().__init__(**kwargs)
        # self.step = 1
        # self.writer = tf.summary.FileWriter(self.log_dir)

    # # Overriding this method to stop creating default log writer
    # def set_model(self, model):
        # pass

    # # Overrided, saves logs with our step number
    # # (otherwise every .fit() will start writing from 0th step)
    # def on_epoch_end(self, epoch, logs=None):
        # self.update_stats(**logs)

    # # Overrided
    # # We train for one batch only, no need to save anything at epoch end
    # def on_batch_end(self, batch, logs=None):
        # pass

    # # Overrided, so won't close writer
    # def on_train_end(self, _):
        # pass

    # # Custom method for saving own metrics
    # # Creates writer, writes custom metrics and closes writer
    # def update_stats(self, **stats):
        # self._write_logs(stats, self.step)

# class DQNAgent:
    # def __init__(self):
        # self.model = self.create_model()
        # self.target_model = self.create_model()
        # self.target_model.set_weights(self.model.get_weights())

        # self.replay_memory = deque(maxlen=REPLAY_MEMORY_SIZE)

        # self.tensorboard = ModifiedTensorBoard(log_dir=f"logs/{MODEL_NAME}-{int(time.time())}")
        # self.target_update_counter = 0
        # self.graph = tf.get_default_graph()

        # self.terminate = False
        # self.last_logged_episode = 0
        # self.training_initialized = False

    # def create_model(self):
        # base_model = Xception(include_top=False, weights= None,input_shape=(IM_HEIGHT,IM_WIDTH,3))

        # x = base_model.output
        # x = GlobalAveragePooling2D()(x)

        # predictions = Dense(3, activation="linear")(x)
        # model = Model(inputs=base_model.input, outputs=predictions)
        # model.compile(loss="mse", optimizer=Adam(lr=0.001), metrics=["accuracy"])
        # return model

    # def update_replay_memory(self, transition):
        # # transition = (current_state, action, reward, new_state, done)
        # self.replay_memory.append(transition)

    # def train(self):
        # if len(self.replay_memory) < MIN_REPLAY_MEMORY_SIZE:
            # return

        # minibatch = random.sample(self.replay_memory, MINIBATCH_SIZE)

        # current_states = np.array([transition[0] for transition in minibatch])/255
        # with self.graph.as_default():
            # current_qs_list = self.model.predict(current_states, PREDICTION_BATCH_SIZE)

        # new_current_states = np.array([transition[3] for transition in minibatch])/255
        # with self.graph.as_default():
            # future_qs_list = self.target_model.predict(new_current_states, PREDICTION_BATCH_SIZE)

        # X = []
        # y = []

        # for index, (current_state, action, reward, new_state, done) in enumerate(minibatch):
            # if not done:
                # max_future_q = np.max(future_qs_list[index])
                # new_q = reward + DISCOUNT * max_future_q
            # else:
                # new_q = reward

            # current_qs = current_qs_list[index]
            # current_qs[action] = new_q

            # X.append(current_state)
            # y.append(current_qs)

        # log_this_step = False
        # if self.tensorboard.step > self.last_logged_episode:
            # log_this_step = True
            # self.last_log_episode = self.tensorboard.step

        # with self.graph.as_default():
            # self.model.fit(np.array(X)/255, np.array(y), batch_size=TRAINING_BATCH_SIZE, verbose=0, shuffle=False, callbacks=[self.tensorboard] if log_this_step else None)


        # if log_this_step:
            # self.target_update_counter += 1

        # if self.target_update_counter > UPDATE_TARGET_EVERY:
            # self.target_model.set_weights(self.model.get_weights())
            # self.target_update_counter = 0

    # def get_qs(self, state):
        # return self.model.predict(np.array(state).reshape(-1, *state.shape)/255)[0]

    # def train_in_loop(self):
        # X = np.random.uniform(size=(1, IM_HEIGHT, IM_WIDTH, 3)).astype(np.float32)
        # y = np.random.uniform(size=(1, 3)).astype(np.float32)
        # with self.graph.as_default():
            # self.model.fit(X,y, verbose=False, batch_size=1)

        # self.training_initialized = True

        # while True:
            # if self.terminate:
                # return
            # self.train()
            # time.sleep(0.01)