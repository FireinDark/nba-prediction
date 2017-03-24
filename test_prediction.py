import pandas as pd
import math
import csv
import random
import numpy as np
from sklearn.model_selection import cross_val_score
from sklearn.linear_model import LogisticRegression
from datetime import datetime

base_elo = 1600
team_elos = {}
X = []
y = []
folder = 'data'

# 计算每个球队的elo值
def calc_elo(win_team, lose_team):
    winner_rank = get_elo(win_team)
    loser_rank = get_elo(lose_team)

    rank_diff = winner_rank - loser_rank
    exp = (rank_diff  * -1) / 400
    odds = 1 / (1 + math.pow(10, exp))
    # 根据rank级别修改K值
    if winner_rank < 2100:
        k = 32
    elif winner_rank >= 2100 and winner_rank < 2400:
        k = 24
    else:
        k = 16
    new_winner_rank = round(winner_rank + (k * (1 - odds)))
    new_rank_diff = new_winner_rank - winner_rank
    new_loser_rank = loser_rank - new_rank_diff

    return new_winner_rank, new_loser_rank

# 根据每支队伍的Miscellaneous Opponent，Team统计数据csv文件进行初始化
def initialize_data(Mstat, Ostat, Tstat):
    new_Mstat = Mstat.drop(['Rk', 'Arena'], axis=1)
    new_Ostat = Ostat.drop(['Rk', 'G', 'MP'], axis=1)
    new_Tstat = Tstat.drop(['Rk', 'G', 'MP'], axis=1)

    team_stats1 = pd.merge(new_Mstat, new_Ostat, how='left', on='Team')
    team_stats1 = pd.merge(team_stats1, new_Tstat, how='left', on='Team')

    return team_stats1.set_index('Team', inplace=False, drop=True)

def get_elo(team):
    try:
        return team_elos[team]
    except:
        # 当最初没有elo时，给每个队伍最初赋base_elo
        team_elos[team] = base_elo
        return team_elos[team]

def build_dataSet(team_stats, all_data):
    print("Building data set..")
    for index, row in all_data.iterrows():

        Hteam = row['Hteam']
        Vteam = row['Vteam']

        Wteam = Hteam
        Lteam = Vteam
        if row['HPTS'] < row['VPTS']:
            Wteam, Lteam = Lteam, Wteam

        #获取最初的elo或是每个队伍最初的elo值
        team1_elo = get_elo(Wteam)
        team2_elo = get_elo(Lteam)

        # 给主场比赛的队伍加上100的elo值
        if Hteam == Wteam:
            team1_elo += 100
        else:
            team2_elo += 100

        # 把elo当为评价每个队伍的第一个特征值
        team1_features = [team1_elo]
        team2_features = [team2_elo]

        # 添加我们从basketball reference.com获得的每个队伍的统计信息
        for key, value in team_stats.loc[Wteam].iteritems():
            team1_features.append(value)
        for key, value in team_stats.loc[Lteam].iteritems():
            team2_features.append(value)

        # 将两支队伍的特征值随机的分配在每场比赛数据的左右两侧
        # 并将对应的0/1赋给y值
        if random.random() > 0.5:
            X.append(team1_features + team2_features)
            y.append(0)
        else:
            X.append(team2_features + team1_features)
            y.append(1)

        # 根据这场比赛的数据更新队伍的elo值
        new_winner_rank, new_loser_rank = calc_elo(Wteam, Lteam)
        team_elos[Wteam] = new_winner_rank
        team_elos[Lteam] = new_loser_rank

    return np.nan_to_num(X), np.array(y)

def predict_winner(team_1, team_2, model, team_stats):
    features = []

    # team 1，客场队伍
    features.append(get_elo(team_1))
    for key, value in team_stats.loc[team_1].iteritems():
        features.append(value)

    # team 2，主场队伍
    features.append(get_elo(team_2) + 100)
    for key, value in team_stats.loc[team_2].iteritems():
        features.append(value)

    features = np.nan_to_num(features)
    return model.predict_proba([features])

def train_model(team_stats_old, team_stats_new, result_data, test_data, weight):
    # 将上个赛季跟本赛季的数据加权求和取均值
    team_stats = team_stats_old.copy()
    for index, row1 in team_stats_old.iterrows():
        row2 = team_stats_new.loc[index]
        row1 = row1 + row2 * weight
        team_stats.ix[index] = row1

    X, y = build_dataSet(team_stats, result_data)

    # 训练网络模型
    print("Fitting on %d game samples.." % len(X))

    model = LogisticRegression()
    model.fit(X, y)

    #利用10折交叉验证计算训练正确率
    print("Doing cross-validation..")
    print(cross_val_score(model, X, y, cv = 10, scoring='accuracy', n_jobs=-1).mean())

    #利用训练好的model在测试集中进行预测
    print('Predicting on test data..')

    result = []
    for index, row in test_data.iterrows():
        team1 = row['Vteam']
        team2 = row['Hteam']
        pred = predict_winner(team1, team2, model, team_stats)
        result.append(pred[0][0])

    return result

def vefify_result(test_data, predict_result):
    success = 0
    index = 0
    for x, row in test_data.iterrows():
        if row['VPTS'] > row['HPTS'] and predict_result[index] >= 0.5:
            success += 1
        if row['VPTS'] < row['HPTS'] and predict_result[index] < 0.5:
            success += 1
        index += 1

    return success * 1.0 / index

if __name__ == '__main__':

    # 读取上个赛季的数据
    Mstat = pd.read_csv(folder + '/15-16Miscellaneous_Stat.csv')
    Ostat = pd.read_csv(folder + '/15-16Opponent_Per_Game_Stat.csv')
    Tstat = pd.read_csv(folder + '/15-16Team_Per_Game_Stat.csv')

    team_stats_old = initialize_data(Mstat, Ostat, Tstat)

    # 读取新赛季的数据
    Mstat = pd.read_csv(folder + '/16-17Miscellaneous_Stat.csv')
    Ostat = pd.read_csv(folder + '/16-17Opponent_Per_Game_Stat.csv')
    Tstat = pd.read_csv(folder + '/16-17Team_Per_Game_Stat.csv')

    team_stats_new = initialize_data(Mstat, Ostat, Tstat)

    # 读取上个赛季的结果数据
    result_old = pd.read_csv(folder + '/15-16Schedule_Result.csv')
    # 读取新赛季的赛程数据
    result_new = pd.read_csv(folder + '/16-17Schedule_Result.csv')

    # 将本赛季已产生的结果跟上赛季的结果融合
    result_count = 0
    for index, row in result_new.iterrows():
        if math.isnan(row['VPTS']):
            break
        result_count += 1

    # 将最近200场数据作为验证集，之前的作为测试集，今后的作为预测集
    result_data = pd.concat([result_old, result_new.loc[0:result_count-200-1]])
    test_data = result_new.loc[result_count-200:result_count-1]
    predict_data = result_new.loc[result_count:]

    max_success_rate = 0
    max_success_weight = 0
    for i in range(0,10):
        X = []
        y = []
        weight = i * 0.1
        print('Training model with weight %f...' % (weight))
        predict_result = train_model(team_stats_old, team_stats_new, result_data, test_data, weight)
        success_rate = vefify_result(test_data, predict_result)
        if success_rate > max_success_rate:
            max_success_rate = success_rate
            max_success_weight = weight

    print(max_success_rate, max_success_weight)