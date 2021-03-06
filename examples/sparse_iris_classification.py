import numpy as np
import torch
import torch.nn.functional as F
import pandas as pd
from sklearn.utils import shuffle
import matplotlib.pyplot as plt

from pagnn.utils.comparisons import FFNN, one_hot, normalize_inplace, count_params, compare
from pagnn.utils.visualize import draw_networkx_graph
from pagnn.pagnn import PAGNNLayer

from rigl_torch.RigL import RigLScheduler


if __name__ == '__main__':
    seed = 666
    if seed is not None:
        torch.manual_seed(seed)
        np.random.seed(seed)

    # load data
    df = pd.read_csv('datasets/iris.csv').dropna()
    df = shuffle(df)

    # normalize data
    # normalize_inplace(df, 'SepalLengthCm')
    # normalize_inplace(df, 'SepalWidthCm')
    # normalize_inplace(df, 'PetalLengthCm')
    # normalize_inplace(df, 'PetalWidthCm')

    # one-hot encodings
    df = one_hot(df, 'Species')

    # separate targets
    filter_col = [col for col in df if col.startswith('Species')]
    targets = df[filter_col]
    df = df.drop(filter_col, axis=1)
    df = df.drop('Id', axis=1)

    D = len(df.columns)
    C = len(targets.columns)
    print('number of data features:', D)
    print('number of classes:', C)

    # split dataset into train & test
    X = torch.tensor(df.to_numpy()).float()
    T = torch.tensor(targets.to_numpy()).float()
    T = torch.argmax(T, dim=1)
    train_perc = 0.67
    split = int(train_perc * X.shape[0])
    train_X, test_X = X[:split], X[split:]
    train_T, test_T = T[:split], T[split:]

    # create data loaders
    batch_size = 10
    train_dl = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(train_X, train_T), batch_size=batch_size)
    test_dl = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(test_X, test_T), batch_size=batch_size)

    epochs = 25
    T_end = int(0.75 * (epochs * len(train_dl))) # for sparsity

    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

    model_dicts = []
    configs = [
        {'num_steps': 1, 'activation': None, 'dense_allocation': 0.3},
        {'num_steps': 2, 'activation': None, 'dense_allocation': 0.3},
        {'num_steps': 3, 'activation': None, 'dense_allocation': 0.3},
        # {'num_steps': 1, 'activation': 'relu'}, # doesn't work
        {'num_steps': 2, 'activation': 'relu', 'dense_allocation': 0.3},
        {'num_steps': 3, 'activation': 'relu', 'dense_allocation': 0.3},
    ]

    for config in configs:
        pagnn_lr = 0.01
        extra_neurons = 0
        n = D + C + extra_neurons
        activation_func = None
        if config['activation'] == 'relu':
            activation_func = F.relu
        pagnn_model = PAGNNLayer(D, C, extra_neurons, steps=config['num_steps'], retain_state=False, activation=activation_func) # graph_generator=nx.generators.classic.complete_graph)
        pagnn_model.to(device)
        name_prefix = ('%i%%_SparsePAGNN' % (int((1-config['dense_allocation'])*100))) if config['dense_allocation'] is not None else 'DensePAGNN'
        if config['activation'] is None:
            model_name = '%s(#p=%i, steps=%i)' % (name_prefix,  count_params(pagnn_model), config['num_steps'])
        else:
            model_name = '%s(#p=%i, steps=%i) + %s' % (name_prefix, count_params(pagnn_model), config['num_steps'], str(config['activation']))

        pagnn_optimizer = torch.optim.Adam(pagnn_model.parameters(), lr=pagnn_lr)

        pruner = None
        if config['dense_allocation'] is not None:
            pruner = RigLScheduler(pagnn_model, pagnn_optimizer, dense_allocation=config['dense_allocation'], T_end=T_end)

        pagnn = {
            'name': model_name,
            'model': pagnn_model,
            # 'num_steps': config['num_steps'],
            'optimizer': pagnn_optimizer,
            'pruner': pruner
        }

        model_dicts.append(pagnn)

    ffnn_lr = 0.01
    ffnn_model = FFNN(D, D, C)
    ffnn_model.to(device)
    ffnn = {
        'name': 'FFNN(%i, %i, %i, #p=%i)' % (D, D, C, count_params(ffnn_model)),
        'model': ffnn_model,
        'optimizer': torch.optim.Adam(ffnn_model.parameters(), lr=ffnn_lr),
    }

    model_dicts.append(ffnn)

    # print('pagnn num params:', sum(p.numel() for p in pagnn_model.parameters()))
    # print('ffnn num params:', sum(p.numel() for p in ffnn_model.parameters()))

    criterion = F.cross_entropy

    compare(model_dicts, train_dl, test_dl, epochs, criterion, test_accuracy=True, device=device)
    
    fig = plt.figure(figsize=(24, 14), dpi=60)
    fig.suptitle('Iris Classification w/ RigL - (Sparse PAGNN vs FFNN)', fontsize=24)

    plt.subplot(211)
    for model_dict in model_dicts:
        plt.plot(model_dict['train_history'], label=model_dict['name'])
    # plt.plot(ffnn['train_history'], label='FFNN (lr: %f)' % ffnn_lr)
    plt.legend()
    plt.title('train loss')

    """
    plt.subplot(222)
    for model_dict in model_dicts:
        plt.plot(model_dict['test_history'], label=model_dict['name'])
    # plt.plot(ffnn['test_history'], label='FFNN')
    plt.legend()
    plt.title('test accuracy')
    """

    plt.subplot(212)
    print('creating graph...')
    pagnn = model_dicts[-2] # get the last pagnn network defined
    draw_networkx_graph(pagnn['model'], mode='scaled_weights')
    plt.title('%s architecture' % pagnn['name'])

    plt.savefig('examples/figures/sparse_iris_classification.png', transparent=True)
    plt.show()
