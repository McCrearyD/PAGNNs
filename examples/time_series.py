import torch
import torch.nn.functional as F
from torch import nn
import numpy as np
from copy import deepcopy
import seaborn as sns
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt

from pagnn.pagnn import PAGNNLayer
from pagnn.utils.comparisons import count_params, LSTM, create_inout_sequences



if __name__ == '__main__':
    seed = 666
    if seed is not None:
        torch.manual_seed(seed)
        np.random.seed(seed)

    flight_data = sns.load_dataset('flights')
    
    # plot passengers over time
    """
    fig_size = plt.rcParams['figure.figsize']
    fig_size[0] = 15
    fig_size[1] = 5
    plt.rcParams['figure.figsize'] = fig_size
    plt.title('Month vs Passenger')
    plt.ylabel('Total Passengers')
    plt.xlabel('Months')
    plt.grid(True)
    plt.autoscale(axis='x',tight=True)
    plt.plot(flight_data['passengers'])
    plt.show()
    """

    all_data = flight_data['passengers'].values.astype(float)
    test_data_size = 12
    train_data = all_data[:-test_data_size]
    test_data = all_data[-test_data_size:]

    scaler = MinMaxScaler(feature_range=(-1, 1))
    train_data_normalized = scaler.fit_transform(train_data .reshape(-1, 1))

    train_data_normalized = torch.FloatTensor(train_data_normalized).view(-1)

    train_window = 12
    train_inout_seq = create_inout_sequences(train_data_normalized, train_window)

    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
    model = LSTM(device=device)
    loss_function = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    pagnn_model = PAGNNLayer(1, 1, 10, steps=1, retain_state=False).to(device)
    pagnn_optimizer = torch.optim.Adam(pagnn_model.parameters(), lr=0.001)

    epochs = 300

    for i in range(epochs):
        pagnn_avg_loss = 0
        lstm_avg_loss = 0

        for seq, labels in train_inout_seq:
            seq = seq.to(device)
            labels = labels.to(device)

            optimizer.zero_grad()
            pagnn_optimizer.zero_grad()

            model.hidden_cell = (torch.zeros(1, 1, model.hidden_layer_size, device=device),
                            torch.zeros(1, 1, model.hidden_layer_size, device=device))
    
            y_pred = model(seq)
            y_pred_pagnn = pagnn_model(seq)

            single_loss = loss_function(y_pred, labels)
            single_loss.backward()
            optimizer.step()

            pagnn_single_loss = loss_function(y_pred_pagnn, labels)
            pagnn_single_loss.backward()
            pagnn_optimizer.step()

            pagnn_avg_loss += pagnn_single_loss.item()
            lstm_avg_loss += single_loss.item()

        pagnn_avg_loss /= len(train_inout_seq)
        lstm_avg_loss /= len(train_inout_seq)
    
        if i%25 == 1:
            print(f'epoch: {i:3} LSTM avg loss: {lstm_avg_loss:10.8f} PAGNN avg loss: {pagnn_avg_loss:10.8f}')

    
    print(f'epoch: {i:3} LSTM avg loss: {lstm_avg_loss:10.10f} PAGNN avg loss: {pagnn_avg_loss:10.10f}')

    fut_pred = 12

    test_inputs = train_data_normalized[-train_window:].tolist()
    pagnn_test_inputs = train_data_normalized[-train_window:].tolist()

    model.eval()
    for i in range(fut_pred):
        seq = torch.FloatTensor(test_inputs[-train_window:]).to(device)
        with torch.no_grad():
            model.hidden = (torch.zeros(1, 1, model.hidden_layer_size, device=device),
                            torch.zeros(1, 1, model.hidden_layer_size, device=device))
            test_inputs.append(model(seq).item())
            pagnn_test_inputs.append(pagnn_model(seq).item())

    actual_predictions = scaler.inverse_transform(np.array(test_inputs[train_window:] ).reshape(-1, 1))
    pagnn_actual_predictions = scaler.inverse_transform(np.array(pagnn_test_inputs[train_window:] ).reshape(-1, 1))

    fig = plt.figure(figsize=(16, 9))
    fig.suptitle('Time Series Prediction - (PAGNN vs LSTM)', fontsize=24)

    plt.subplot(211)
    x = np.arange(132, 144, 1)
    plt.title('Month vs Passenger')
    plt.ylabel('Total Passengers')
    plt.grid(True)
    plt.autoscale(axis='x', tight=True)
    plt.plot(flight_data['passengers'], label='Ground Truth')
    plt.plot(x,actual_predictions, label='LSTM predictions')
    plt.plot(x,pagnn_actual_predictions, label='PAGNN predictions')
    plt.legend()

    plt.title('Month vs Passenger')
    plt.ylabel('Total Passengers')
    plt.grid(True)
    plt.autoscale(axis='x', tight=True)
    
    plt.subplot(212)
    plt.plot(flight_data['passengers'][-train_window:], label='Ground Truth')
    plt.plot(x,actual_predictions, label='LSTM predictions (%i params)' % count_params(model))
    plt.plot(x,pagnn_actual_predictions, label='PAGNN predictions (%i params)' % count_params(pagnn_model))
    plt.legend()
    plt.savefig('examples/figures/time_series.png', transparent=True)
    plt.show()
