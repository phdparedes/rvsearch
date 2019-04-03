"""Utilities for loading data, checking for known planets, etc."""

import numpy as np
import scipy
import pandas as pd
import radvel
try:
    import cpsutils
    from cpsutils import io
except:
    RuntimeError()


"""Functions for posterior modification (resetting, intializing, etc.)
"""


def reset_params(post, default_pdict):
    # Reset post.params values to default values
    for k in default_pdict.keys():
        post.params[k].value = default_pdict[k]
    return post


def initialize_default_pars(instnames=['inst'], fitting_basis='per tc secosw sesinw k'):
    """Set up a default Parameters object.

    None of the basis values are free params, for the initial 0-planet fit.
    Remember to reset .vary to True for all relevant params.

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
    params['per1'].vary = False

    return params


def initialize_post(data, params=None, priors=[]):
    """Initialize a posterior object with data, params, and priors.
    Args:
        data: a pandas dataframe.
        params: a list of radvel parameter objects.
        priors: a list of priors to place on the posterior object.
    Returns:
        post (radvel Posterior object)

    """

    if params is None:
        # params = radvel.Parameters(1, basis='per tc secosw sesinw logk')
        params = initialize_default_pars(instnames=data.tel)
    iparams = radvel.basis._copy_params(params)

    # Allow for time to be listed as 'time' or 'jd' (Julian Date).
    if {'jd'}.issubset(data.columns):
        data['time'] = data['jd']

    # initialize RVModel
    time_base = np.mean([data['time'].max(), data['time'].min()])
    mod = radvel.RVModel(params, time_base=time_base)

    # initialize Likelihood objects for each instrument
    telgrps = data.groupby('tel').groups
    likes = {}

    for inst in telgrps.keys():
        likes[inst] = radvel.likelihood.RVLikelihood(
            mod, data.iloc[telgrps[inst]].time, data.iloc[telgrps[inst]].mnvel,
            data.iloc[telgrps[inst]].errvel, suffix='_'+inst)

        likes[inst].params['gamma_'+inst] = iparams['gamma_'+inst]
        likes[inst].params['jit_'+inst] = iparams['jit_'+inst]
    # Can this be cleaner? like = radvel.likelihood.CompositeLikelihood(likes)
    like = radvel.likelihood.CompositeLikelihood(list(likes.values()))

    post = radvel.posterior.Posterior(like)
    if priors == []:
        priors.append(radvel.prior.PositiveKPrior(post.params.num_planets))
        priors.append(radvel.prior.EccentricityPrior(post.params.num_planets))
    # priors.append([radvel.prior.HardBounds('jit_'+inst, 0.0, 20.0)
    # for inst in telgrps.keys()])
    post.priors = priors

    return post


def window(times, freqs, plot=False):
    """Function to generate, and plot, the window function of observations.

    Args:
        time: times of observations in a dataset. FOR SEPARATE TELESCOPES?

    """
    W = np.zeros(len(freqs))
    for i, freq in enumerate(freqs):
        W[i] = np.absolute(np.sum(np.exp(-2*np.pi*1j*times*freq)))
    W /= float(len(times))
    return W

def read_from_csv(filename, binsize=0.0, verbose=True):
    """Read radial velocity data from a csv file into a Pandas dataframe.

    Args:
        filename (string): Path to csv file
        binsize (float): Times in which to bin data, in given units
        verbose (bool): Notify user if instrument types not given?

    """
    data = pd.read_csv(filename)
    if 'tel' not in data.columns:
        if verbose:
            print('Instrument types not given.')
        data['tel'] = 'Inst'
    if binsize > 0.0:
        if 'time' in data.columns:
            t = data['time'].values
            tkey = 'time'
        elif 'jd' in data.columns:
            t = data['jd'].values
            tkey = 'jd'
        else:
            raise ValueError('Incorrect data input.')
        time, mnvel, errvel, tel = radvel.utils.bintels(t, data['mnvel'].values,
                                                        data['errvel'].values,
                                                        data['tel'].values,
                                                        binsize=binsize)
        bin_dict = {tkey: time, 'mnvel': mnvel,
                    'errvel': errvel, 'tel': tel}
        data = pd.DataFrame(data=bin_dict)

    return data


def read_from_arrs(t, mnvel, errvel, tel=None, verbose=True):
    data = pd.DataFrame()
    data['time'], data['mnvel'], data['errvel'] = t, mnvel, errvel
    if tel == None:
        if verbose:
            print('Instrument type not given.')
        data['tel'] = 'Inst'
    else:
        data['tel'] = tel
    return data


def read_from_vst(filename, verbose=True):
    """Read radial velocity data from a vst file into a Pandas dataframe.

    Args:
        filename (string): Path to csv file
        verbose (bool): Notify user if instrument types not given?

    Note:
        Only relevant for HIRES users.

    """
    b = io.read_vst(filename)
    data = pd.DataFrame()
    data['time'] = b.jd
    data['mnvel'] = b.mnvel
    data['errvel'] = b.errvel
    data['tel'] = 'HIRES'

    data.to_csv(filename[:-3]+'csv')

    return data


# Function for collecting results of searches in current directory.
def scrape(starlist, star_db_name=None, filename='system_props.csv'):
    """Take data from completed searches and compile into one dataframe.

    Args:
        starlist (list): List of starnames to access in current directory
        star_db_name (string [optional]): Filename of star properties dataframe
        filename (string): Path to which to save dataframe

    Note:
        If specified, compute planet masses and semi-major axes.

    """
    all_params = []
    nplanets = []

    for star in starlist:
        params = dict()
        params['name'] = star
        try:
            post = radvel.posterior.load(star+'/post_final.pkl')
        except (RuntimeError, FileNotFoundError):
            print('Not done looking for planets around {} yet, \
                                try again later.'.format(star))
            continue

        if post.params.num_planets == 1:
            if post.params['k1'].value == 0.:
                num_planets = 0
            else:
                num_planets = 1
            nplanets.append(num_planets)
        else:
            num_planets = post.params.num_planets
            nplanets.append(num_planets)
        params['num_planets'] = num_planets

        for k in post.params.keys():
            params[k] = post.params[k].value
        all_params.append(params)

    # Save radvel parameters as a pandas dataframe.
    props = pd.DataFrame(all_params)

    if star_db_name is not None:
        try:
            star_db = pd.read_csv(star_db_name)
        except (RuntimeError, FileNotFoundError):
            print('That is not a pandas dataframe. Try again.')

        # Add enough columns to for searched system with most planets.
        max_num_planets = np.amax(nplanets)
        for n in np.arange(1, max_num_planets+1):
            props['Mstar'] = np.nan
            props['M{}'.format(n)] = np.nan
            props['a{}'.format(n)] = np.nan

        # Save median star mass, uncertainties
        for star in starlist:
            try:
                props_index = props.index[props['name'] == str(star)][0]
                star_index = star_db.index[star_db['name'] == str(star)][0]
            except IndexError:
                continue
            # Save star mass, to be used in planet mass & semi-major axis calculations.
            Mtot = star_db.loc[star_index, 'mstar']
            props.loc[props_index, 'Mstar'] = Mtot

            # For each found planet, compute mass and semi-major axis
            if props.loc[props_index, 'num_planets'] != 0:
                for n in np.arange(1, props.loc[props_index, 'num_planets']+1):
                    K = props.loc[props_index, 'k{}'.format(n)]
                    P = props.loc[props_index, 'per{}'.format(n)]
                    e = props.loc[props_index, 'secosw{}'.format(n)]**2 + \
                        props.loc[props_index, 'sesinw{}'.format(n)]**2
                    props.loc[props_index, 'M{}'.format(n)] = \
                        radvel.utils.Msini(K, P, Mtot, e, Msini_units='jupiter')
                    props.loc[props_index, 'a{}'.format(n)] = \
                        radvel.utils.semi_major_axis(P, Mtot)

    props.to_csv('system_props.csv')
    return props


def cartesian_product(*arrays):
    """
        Generate a cartesian product of input arrays.

    Args:
        arrays (arrays): 1-D arrays to form the cartesian product of.

    Returns:
        array: cartesian product of input arrays
    """

    la = len(arrays)
    dtype = np.result_type(*arrays)
    arr = np.empty([len(a) for a in arrays] + [la], dtype=dtype)
    for i, a in enumerate(np.ix_(*arrays)):
        arr[..., i] = a

    return arr.reshape(-1, la)


# Test search-specific priors
'''
class Beta(Prior):
    """Beta prior
    Beta prior on a given parameter. Default is Kipping eccentricity prior.
    Args:
        param (string): parameter label
        mu (float): center of Gaussian prior
        sigma (float): width of Gaussian prior
    """

    def __init__(self, alpha=0.867, beta=3.03, param):
        self.alpha = alpha
        self.beta = beta
        self.param = param

    def __call__(self, params):
        x = params[self.param].value
        return -0.5 * ((x - self.mu) / self.sigma)**2 - 0.5*np.log((self.sigma**2)*2.*np.pi)

    def __repr__(self):
        s = "Beta prior on {}, alpha={}, beta={}".format(
            self.param, self.alpha, self.beta
            )
        return s

    def __str__(self):
        try:
            tex = model.Parameters(9).tex_labels(param_list=[self.param])[self.param]

            s = "Beta prior on {}: $\\alpha={}, \\beta={}$ \\\\".format(tex, self.alpha, self.beta)
        except KeyError:
            s = self.__repr__()

        return s
'''
