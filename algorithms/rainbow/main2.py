"""
Adapted from https://github.com/Kaixhin/Rainbow

The main file needed within rainbow. Runs of the train and test functions from their respective
files.

Example of use:
`cd algorithms/rainbow`
`python main.py`

Runs Rainbow DQN on our AI2ThorEnv wrapper with default params. Optionally it can be run on any
atari environment as well using the "game" flag, e.g. --game seaquest.
"""

import argparse
from datetime import datetime

import numpy as np
import torch

from agent import Agent
from env import Env, FrameStackEnv
from memory import ReplayMemory
from test import test
from gym_ai2thor.envs.ai2thor_env import AI2ThorEnv
import matplotlib.pyplot as plt


parser = argparse.ArgumentParser(description='Rainbow')
parser.add_argument('--seed', type=int, default=123, help='Random seed')
parser.add_argument('--disable-cuda', action='store_true', help='Disable CUDA')
""" Game can be ai2thor to use our wrapper or one atari rom from the list here:
    https://github.com/openai/atari-py/tree/master/atari_py/atari_roms """
parser.add_argument('--game', type=str, default='ai2thor', help='ATARI game or environment')
parser.add_argument('--max-num-steps', type=int, default=int(5000000), metavar='STEPS',
                    help='Number of training steps')
parser.add_argument('--max-episode-length', type=int, default=int(1e3), metavar='LENGTH',
                    help='Max episode length (0 to disable)')
parser.add_argument('--history-length', type=int, default=1, metavar='T',
                    help='Number of consecutive states processed')
parser.add_argument('--hidden-size', type=int, default=512, metavar='SIZE',
                    help='Network hidden size')
parser.add_argument('--noisy-std', type=float, default=0.8, metavar='σ',
                    help='Initial standard deviation of noisy linear layers')
parser.add_argument('--num-atoms', type=int, default=51, metavar='C',
                    help='Discretised size of value distribution')
parser.add_argument('--V-min', type=float, default=-10, metavar='V',
                    help='Minimum of value distribution support')
parser.add_argument('--V-max', type=float, default=10, metavar='V',
                    help='Maximum of value distribution support')
parser.add_argument('--model-path', type=str, metavar='PARAMS', help='Pretrained model (state dict)')
parser.add_argument('--memory-capacity', type=int, default=int(1e6), metavar='CAPACITY',
                    help='Experience replay memory capacity')
parser.add_argument('--replay-frequency', type=int, default=1, metavar='k',
                    help='Frequency of sampling from memory')
parser.add_argument('--priority-exponent', type=float, default=0.1, metavar='ω',
                    help='Prioritised experience replay exponent (originally denoted α)')
parser.add_argument('--priority-weight', type=float, default=0.4, metavar='β',
                    help='Initial prioritised experience replay importance sampling weight')
parser.add_argument('--multi-step', type=int, default=3, metavar='n',
                    help='Number of steps for multi-step return')
parser.add_argument('--discount', type=float, default=0.99, metavar='γ',
                    help='Discount factor')
parser.add_argument('--target-update', type=int, default=int(32e3), metavar='τ',
                    help='Number of steps after which to update target network')
parser.add_argument('--reward-clip', type=int, default=0, metavar='VALUE',
                    help='Reward clipping (0 to disable)')
parser.add_argument('--lr', type=float, default=0.0000625, metavar='η',
                    help='Learning rate')
parser.add_argument('--adam-eps', type=float, default=1.5e-4, metavar='ε',
                    help='Adam epsilon')
parser.add_argument('--batch-size', type=int, default=32, metavar='SIZE',
                    help='Batch size')
parser.add_argument('--learn-start', type=int, default=int(20e3), metavar='STEPS',
                    help='Number of steps before starting training')
parser.add_argument('--evaluate-only', action='store_true', help='Evaluate only')
parser.add_argument('--evaluation-interval', type=int, default=1e5, metavar='STEPS',
                    help='Number of training steps between evaluations')
parser.add_argument('--evaluation-episodes', type=int, default=10, metavar='N',
                    help='Number of evaluation episodes to average over')
parser.add_argument('--evaluation-size', type=int, default=500, metavar='N',
                    help='Number of transitions to use for validating Q')
parser.add_argument('--log-interval', type=int, default=200, metavar='STEPS',
                    help='Number of training steps between logging status')
parser.add_argument('--render', action='store_true', default=False,
                    help='Display screen (testing only)')
parser.add_argument('--config-file', type=str, default='config_files/rainbow_example.json',
                    help='Config file used for ai2thor environment definition')

# Setup arguments, seeds and cuda
args = parser.parse_args()

# Checkpoints
def save_checkpoint(state, filename='checkpoint.pth.tar'):
    torch.save(state, filename)

# Save Model
def save_model(self, filename='model.pth'):
    torch.save(self.online_net.state_dict(), filename)

# Generate Plots
# Define plotting function
def plot_training_metrics(train_losses, avg_rewards, avg_qs, eval_rewards, eval_qs, evaluation_interval, num_steps):
    fig, axs = plt.subplots(2, 2, figsize=(15, 10))
    print(num_steps)
    print(len(avg_qs))
    print(len(avg_rewards))
    # Plot Training Loss

    # Plot Average Reward per Episode
    axs[0, 0].plot(avg_rewards, label='Avg. Reward per Episode')
    axs[0, 0].set_title('Average Reward per Episode')
    axs[0, 0].set_xlabel('Episode')
    axs[0, 0].set_ylabel('Reward')
    axs[0, 0].legend()

    # Plot Average Q-value per Step
    axs[1, 0].plot(avg_qs, label='Avg. Q-value per Step')
    axs[1, 0].set_title('Average Q-value per Step')
    axs[1, 0].set_xlabel('Training Steps')
    axs[1, 0].set_ylabel('Q-value')
    axs[1, 0].legend()

    # Plot Evaluation Metrics
    steps = range(0, len(eval_rewards) * evaluation_interval, evaluation_interval)
    axs[1, 1].plot(steps, eval_rewards, label='Avg. Reward')
    axs[1, 1].plot(steps, eval_qs, label='Avg. Q-value')
    axs[1, 1].set_title('Evaluation Metrics')
    axs[1, 1].set_xlabel('Training Steps')
    axs[1, 1].set_ylabel('Metric Value')
    axs[1, 1].legend()

    plt.tight_layout()
    plt.xlim(0, 999)

    plt.show()

if __name__ == '__main__':
    rewards_history = []
    Q_values_history = []
    steps_history = []
    checkpoint_interval = 10000
    num_episodes = 1000  # Number of episodes to average over
    num_steps = 1000  # Number of training steps
    evaluation_episodes = 10  # Number of episodes for evaluation
    max_episode_length = 1000  # Maximum length of each episode
    render = False  # Whether to render the environment during evaluation
    
    print('-' * 10 + '\n' + 'Options' + '\n' + '-' * 10)
    for k, v in vars(args).items():
        print(' ' * 4 + k + ': ' + str(v))
    np.random.seed(args.seed)
    torch.manual_seed(np.random.randint(1, 10000))
    if torch.cuda.is_available() and not args.disable_cuda:
        args.device = torch.device('cuda')
        torch.cuda.manual_seed(np.random.randint(1, 10000))
        # Disable non deterministic ops (not sure if critical but better safe than sorry)
        torch.backends.cudnn.enabled = False
    else:
        args.device = torch.device('cpu')

    # Simple ISO 8601 timestamped logger
    def log(s):
        print('[' + str(datetime.now().strftime('%Y-%m-%dT%H:%M:%S')) + '] ' + s)

    # Environment selection
    if args.game == 'ai2thor':
        env = FrameStackEnv(AI2ThorEnv(config_file=args.config_file), args.history_length,
                            args.device)
        args.resolution = env.config['resolution']
        args.img_channels = env.observation_space.shape[0]
    else:
        env = Env(args)
        env.train()
        args.resolution = (84, 84)
        args.img_channels = 1
    action_space = env.action_space

    # Agent
    dqn = Agent(args, env)
    mem = ReplayMemory(args, args.memory_capacity)
    """ Priority weights are linearly annealed and increase every step by priority_weight_increase from 
    args.priority_weight to 1. 
    Typically, the unbiased nature of the updates is most important near convergence at the end of 
    training, as the process is highly non-stationary anyway, due to changing policies, state 
    distributions and bootstrap targets, that small bias can be ignored in this context.
    """
    priority_weight_increase = (1 - args.priority_weight) / (args.max_num_steps - args.learn_start)

    """ Construct validation memory. The transitions stored in this memory will remain constant for 
    the whole training process. During training this gives us a "fixed" evaluation dataset to see
    how the agent's confidence of its performance is improving. 
    """
    val_mem = ReplayMemory(args, args.evaluation_size)
    mem_steps, done = 0, True
    for mem_steps in range(args.evaluation_size):
        if done:
            state, done = env.reset(), False
        next_state, _, done, _ = env.step(env.action_space.sample())
        # No need to store actions or rewards because we only use the state to evaluate Q
        val_mem.append(state, None, None, done)
        state = next_state

    train_losses = []
    avg_rewards = []
    avg_qs = []
    eval_rewards = []
    eval_qs = []

    episode_reward = 0

    if args.evaluate_only:
        dqn.eval()  # Set DQN (online network) to evaluation mode
        avg_reward, avg_Q = test(env, mem_steps, args, dqn, val_mem, evaluate_only=True)
        print('Avg. reward: ' + str(avg_reward) + ' | Avg. Q: ' + str(avg_Q))
    else:
        # Training loop
        dqn.train()
        num_steps, num_episodes, done = 0, 0, True
        # avg_rewards = []
        avg_Q_values = []
        while num_steps < args.max_num_steps:
            if done:
                state, done = env.reset(), False
                episode_reward = 0
            if num_steps % args.replay_frequency == 0:
                dqn.reset_noise()  # Draw a new set of noisy epsilons

            action = dqn.act(state)  # Choose an action greedily (with noisy weights)
            next_state, reward, done, _ = env.step(action)  # Step
            if args.reward_clip > 0:
                reward = max(min(reward, args.reward_clip), -args.reward_clip)  # Clip rewards
            mem.append(state, action, reward, done)  # Append transition to memory
            num_steps += 1
            episode_reward += reward

            if num_steps % args.log_interval == 0:
                log('num_steps = ' + str(num_steps) + ' / ' + str(args.max_num_steps))

            # Train and test
            if num_steps >= args.learn_start:
                # Anneal importance sampling weight β to 1
                mem.priority_weight = min(mem.priority_weight + priority_weight_increase, 1)

                if num_steps % args.replay_frequency == 0:
                    dqn.learn(mem)  # Train with n-step distributional double-Q learning

                if num_steps % args.evaluation_interval == 0:
                    dqn.eval()  # Set DQN (online network) to evaluation mode. Fixed linear layers
                    
                    # Test and save best model
                    avg_reward, avg_Q = test(env, num_steps, args, dqn, val_mem)
                    avg_rewards.append(avg_reward)
                    avg_Q_values.append(avg_Q)
                    log('num_steps = ' + str(num_steps) + ' / ' + str(args.max_num_steps) +
                        ' | Avg. reward: ' + str(avg_reward) + ' | Avg. Q: ' + str(avg_Q))

                    eval_rewards.append(avg_reward)
                    eval_qs.append(avg_Q)
                    if num_steps >= args.max_num_steps:
                        break
                    dqn.train()  # Set DQN (online network) back to training mode

                # Update target network
                if num_steps % args.target_update == 0:
                    dqn.update_target_net()
            state = next_state

             # Collect and append metrics
            if num_steps % args.log_interval == 0:
                log('num_steps = ' + str(num_steps) + ' / ' + str(args.max_num_steps))

            # Calculate average reward per episode and append to avg_rewards
            if done:
                avg_rewards.append(episode_reward)
                episode_reward = 0

            # Calculate average Q-value per step and append to avg_qs
            if num_steps % args.log_interval == 0:
                with torch.no_grad():
                    q_values = dqn.act(state)  # Get Q-values for all actions
                    if isinstance(q_values, int):  # Check if q_values is an integer
                        q_values = torch.tensor([q_values], dtype=torch.float32, device=args.device)  # Convert to tensor
                avg_q = q_values.mean().item()
                avg_qs.append(avg_q)
            
        plot_training_metrics(train_losses, avg_rewards, avg_qs, eval_rewards, eval_qs, int(args.evaluation_interval), num_steps)
        # Save final model
        dqn.save_model(filename='final_model.pth') 
    env.close() 