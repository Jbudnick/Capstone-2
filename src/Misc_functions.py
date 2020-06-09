from src.data_clean_script import replace_with_moving_averages

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def series_to_supervised(data, columns, n_in=1, n_out=1, dropnan=True):
    """
    Frame a time series as a supervised learning dataset.
    Arguments:
        data: Sequence of observations as a list or NumPy array.
        n_in: Number of lag observations as input (X).
        n_out: Number of observations as output (y).
        dropnan: Boolean whether or not to drop rows with NaN values.
    Returns:
        Pandas DataFrame of series framed for supervised learning.
    """
    n_vars = 1 if type(data) is list else data.shape[1]
    df = pd.DataFrame(data)
    cols, names = list(), list()
    # input sequence (t-n, ... t-1)
    for i in range(n_in, 0, -1):
        cols.append(df.shift(i))
        names += [('%s(t-%d)' % (columns[j], i)) for j in range(n_vars)]
    # forecast sequence (t, t+1, ... t+n)
    for i in range(0, n_out):
        cols.append(df.shift(-i))
        if i == 0:
            names += [('%s(t)' % (columns[j])) for j in range(n_vars)]
        else:
            names += [('%s(t+%d)' % (columns[j], i)) for j in range(n_vars)]
    # put it all together
    agg = pd.concat(cols, axis=1)
    agg.columns = names
    # drop rows with NaN values
    if dropnan:
        agg.dropna(inplace=True)
    return agg


def fill_diagonals(df, preds, model, start_row=31, n_interval=21):
    df.fillna(0, inplace=True)
    n_rows = df.shape[0]
    new_preds = list(preds.values)
    for row in range(start_row, n_rows)[:]:
        new_pred = model.predict(df[row:row + 1])[0]
        new_preds.append(new_pred)
        j = 0
        for col in range(n_interval-1, 0, -1):
            try:
                if df.iloc[row + j, col] == 0:
                    df.iloc[row + j, col] = new_pred
                j += 1
            except:
                continue
    new_pred = model.predict(df[-1:-2:-1])[0]
    new_preds.append(new_pred)
    return df, new_preds

def generate_prediction_df(level, total_x, total_y, rf, predictions=21):
    '''
    Generates a pandas Dataframe out into the future. Uses predictions with time lags on future predictions.

    INPUT:
        level: 'High', 'Medium', or 'Low' or custom list of social distancing parameters
        total_x: Feature matrix (not including target) with all features and time series lags included
        total_y: Target values from total_x
        rf: Random Forest Model
        Predictions: Time lagged features to predict out toward future
        
    OUTPUT:
        Dataframe with estimated time lags populated and social distancing levels populated
        Series with estimated target values for each row in dataframe

    '''
    #Part 1: Expands time lagged Daily New Cases columns


    columns = ['days_elapsed(t)', 'retail_and_recreation(t)', 'grocery_and_pharmacy(t)',
               'parks(t)', 'transit_stations(t)', 'workplaces(t)', 'residential(t)', 'driving(t)', 'pop_density(t)']

    levelDict = {'High': [0.34, 0.5, 0.36, 0.295, 0.4, 1.3, 0.385],
                 'Medium': [0.6, 0.8, 0.7, 0.7, 0.75, 1.1, 0.7],
                 'Low': [1, 1, 1, 1, 1, 0.9, 1]
                 }

    if type(level) != str:
        pred_params = level
    else:
        pred_params = levelDict[level]

    pred_df = total_x.copy()
    last_recorded_day = int(pred_df['days_elapsed(t)'].max())
    pop_dens = pred_df['pop_density(t)'].mode().iloc[0]

    for i in range(last_recorded_day + 1, last_recorded_day + predictions + 1):
        pred_df_row = pd.DataFrame([i] + pred_params + [pop_dens]).T
        pred_df_row.columns = columns
        pred_df = pred_df.append(pred_df_row, sort=False)

    y_pred = total_y

    # Part 2: Fills in blank known new cases values
    n_rows = pred_df.shape[0]
    pred_df.fillna(0, inplace=True)
    try:
        row_start = pred_df.shape[0] - pred_df[pred_df['New_Cases_per_pop(t-1)'] == 0].count()[0]
    except:
        row_start = pred_df.shape[0] - \
            pred_df[pred_df['Daily_Cases_per_pop(t-1)'] == 0].count()[0]
    col_start = 20
    new_preds = list(y_pred.values)
    pred_df.iloc[row_start, col_start] = y_pred.values[-1]
    for row in range(row_start, n_rows):
        for col in range(col_start - 1, -1, -1):
            pred_df.iloc[row, col] = pred_df.iloc[row - 1, col + 1]

    #Part 3: Fills in rest of time lagged values for future t values, predicting based on prior predictions
    fill_diag_and_predictions = fill_diagonals(
        pred_df, y_pred.loc[:45], rf.model, start_row=row_start, n_interval=21)
    pred_df = fill_diag_and_predictions[0]
    pred_y = fill_diag_and_predictions[1][-pred_df.shape[0]:]
    return pred_df, pred_y


def find_nearest(array, value):
    idx = (np.abs(array - value)).argmin()
    return idx

def normalize_days(states, covid_df, percent_max=0.25, plot=False, save_x_starts = False):
    '''
    Process covid_df day elapsed column into days elapsed since hitting percent_max of its maximum number of cases/person.
    save_x_starts will return a tuple to translate back into actual date later.

    '''
    state_dfs = []
    x_starts = []
    if plot == True:
        colors = ['red', 'blue', 'green', 'black', 'violet', 'orange']
        fig, ax = plt.subplots(figsize=(12, 6))
    for i, state in enumerate(states):
        raw = covid_df[covid_df['state'] == state]
        df = replace_with_moving_averages(raw, ['New_Cases_per_pop'], 0)
        x = df['days_elapsed']
        y = df['New_Cases_per_pop']
        y_start = max(y) * percent_max
        y_idx = find_nearest(y.values, y_start)
        x_start = x[y == y.iloc[y_idx]].values[0]
        df['days_elapsed'] = df['days_elapsed'] - x_start
        df.rename(columns = {'days_elapsed': 'days_since_start'}, inplace = True)

        if plot == True:
            plt.plot(df['days_since_start'], y, c=colors[i], label=state)
            # ax.axhline(y_start, c=colors[i], lw=2, ls='-.')
            ax.set_title('Day Normalization Plot')
            ax.legend()
        state_dfs.append(df)
        x_starts.append(x_start)
    if save_x_starts == True:
        return x_starts, state_dfs
    return state_dfs

