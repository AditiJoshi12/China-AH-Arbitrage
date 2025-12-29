# kalman.py
import numpy as np
import pandas as pd
from pykalman import KalmanFilter

def kalman_beta(A, H):
    idx = A.index
    A = A.values
    H = H.values

    n = len(A)

    # Observation matrix must be (T, n_dim_obs, n_dim_state)
    obs_mat = H.reshape(n, 1, 1)

    delta = 1e-5
    trans_cov = delta / (1 - delta)

    kf = KalmanFilter(
        n_dim_obs=1,
        n_dim_state=1,
        transition_matrices=np.array([[1]]),
        observation_matrices=obs_mat,
        observation_covariance=1.0,
        transition_covariance=trans_cov,
        initial_state_mean=0.0,
        initial_state_covariance=1.0
    )

    state_means, _ = kf.filter(A)

    return pd.Series(state_means.flatten(), index=idx)
