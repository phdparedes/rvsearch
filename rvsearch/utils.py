#Utilities for loading data, checking for known planets, etc.
import numpy as np
import pandas as pd
import radvel

"""Functions for posterior modification (resetting parameters, intializing, etc.)
"""

def reset_params(post, default_pdict):
	#Reset post.params values to default values
	for k in default_pdict.keys():
		post.params[k].value = default_pdict[k]
	return post

def initialize_default_pars(instnames=['HIRES'], fitting_basis='per tc secosw sesinw k'):
    """Set up a default Parameters object. None of the basis values are free params,
    for the initial 0-planet fit. Remember to reset .vary to True for all relevant params.

    To be used when first starting planet search, with no known planets.

    Args:
        instnames (list): codes of instruments used
        fitting_basis: optional

    Returns:
        Parameters object
    """

    anybasis_params = radvel.Parameters(num_planets=1, basis='per tc e w k')

    anybasis_params['tc1'] = radvel.Parameter(value=2455200.0)
    anybasis_params['w1'] = radvel.Parameter(value=np.pi/2.)
    anybasis_params['k1'] = radvel.Parameter(value=0.0)
    anybasis_params['e1'] = radvel.Parameter(value=0.0)
    anybasis_params['per1'] = radvel.Parameter(value=100.0)

    anybasis_params['dvdt'] = radvel.Parameter(value=0.0)
    anybasis_params['curv'] = radvel.Parameter(value=0.0)

    for inst in instnames:
        anybasis_params['gamma_'+inst] = radvel.Parameter(value=0.0)
        anybasis_params['jit_'+inst] = radvel.Parameter(value=2.0)

    params = anybasis_params.basis.to_any_basis(anybasis_params, fitting_basis)

    params['secosw1'].vary = False
    params['sesinw1'].vary = False
    params['k1'].vary = False
    params['per1'].vary = False
    params['tc1'].vary = False

    return params

def initialize_post(data, params=None, priors=None):
    """Initialize a posterior object with data, params, and priors.
    Args:
        data: a pandas dataframe.
    Returns:
        post (radvel Posterior object)

	TO-DO: MAKE OPTION FOR KNOWN MULTI-PLANET POSTERIOR
    """

    if params == None:
        params = radvel.Parameters(1, basis='per tc secosw sesinw logk')
    iparams = radvel.basis._copy_params(params)

    #initialize RVModel
    time_base = np.mean([data['time'].max(), data['time'].min()])
    mod = radvel.RVModel(params, time_base=time_base)

    #initialize Likelihood objects for each instrument
    telgrps = data.groupby('tel').groups
    likes = {}

    for inst in telgrps.keys():
        likes[inst] = radvel.likelihood.RVLikelihood(
            mod, data.iloc[telgrps[inst]].time, data.iloc[telgrps[inst]].mnvel,
            data.iloc[telgrps[inst]].errvel, suffix='_'+inst)

        likes[inst].params['gamma_'+inst] = iparams['gamma_'+inst]
        likes[inst].params['jit_'+inst] = iparams['jit_'+inst]
	#Can this be cleaner? like = radvel.likelihood.CompositeLikelihood(likes), if likes is array, not dic.
    like = radvel.likelihood.CompositeLikelihood(list(likes.values()))

    post = radvel.posterior.Posterior(like)
	#FIX TO COMBINE GIVEN PRIORS AND NEEDED PRIORS
    if priors != None:
        post.priors = priors
    #else:
    #    priors = [radvel.prior.HardBounds('jit_'+inst, 0.0, 20.0) for inst in telgrps.keys()]
    #    post.priors = priors
    return post

"""Series of functions for reading data from various sources into pandas dataframes.
"""
def read_from_csv(filename, verbose=True):
    data = pd.read_csv(filename)
    if 'tel' not in data.columns:
        if verbose:
            print('Telescope type not given, defaulting to HIRES.')
        data['tel'] = 'HIRES'
        #Question: DO WE NEED TO CONFIRM VALID TELESCOPE TYPE?
    return data

def read_from_arrs(t, mnvel, errvel, tel=None, verbose=True):
    data = pd.DataFrame()
    data['time'], data['mnvel'], data['errvel'] = t, mnvel, errvel
    if tel == None:
        if verbose:
            print('Telescope type not given, defaulting to HIRES.')
        data['tel'] = 'HIRES'
    else:
        data['tel'] = tel
    return data
