from cyvcf2 import VCF
import os
import numpy as np
import pandas as pd
import subprocess
import collections
from scipy.stats import *
import math
from . import thread_wrapping as tw


"""
Compute the imputation errors.
Vertically: read chunks of 1000 markers.
Plot different analysis.
"""
# TODO: Unphased poolning och prephasa data: kör Beagle med eller uten referens data set?
# TODO: Köra ny experiment med 100 000 markörer
# TODO: try to characterize behav# TODO: try to characterize behavior of markers


### TOOLS

def per_site_sample_error(elem2x2):
    """
    Computes the imputation error as the distance between
    the true data set vs. imputed at one site for one sample.
    :param elem2x2: 2*2 array representing the pair of GTs to compare.
    Ex. 0|0  vs. 1|0 = [[0 0] [0 1]]
    :return: integer score for error: 0 = right, > 0 = wrong
    """
    return np.array(abs(elem2x2[:2].sum() - elem2x2[2:].sum()))


def para_array(arr1, arr2):
    """
    Merge the two data sets to compare, adding 1 dimension.
    :param arr1: array of genotypes values
    :param arr2: array of genotypes values
    :return: array of genotypes values
    """
    return np.stack([arr1, arr2], axis=-1)


def per_element_error(arr4d, ax):
    """
    Computes imputation error row- or column-wise
    :param arr4d: data sets to compare
    :param ax: axis over which to apply the cumulative sum
    :return: 3d-array of error values from the compared data sets
    """
    arr = np.rollaxis(arr4d, ax)
    arr2d = np.reshape(arr, (arr.shape[0]*arr.shape[1], 2*2))
    errors =  np.apply_along_axis(per_site_sample_error, 1, arr2d)
    return errors.reshape(arr.shape[0], arr.shape[1])


def per_axis_error(arr4d, ax):
    """
       Cumulates error row- or column-wise
       :param arr4d: data sets to compare
       :param ax: axis over which to apply the cumulative sum
       :return: 1d-array of error values along the ax-axis
       """
    return per_element_error(arr4d, ax).sum(axis=1)/arr4d.shape[ax]


def vcf2array(vcf_obj, size):
    """
    Throws the genotypes values of a VCF file into an array.
    :param vcf_obj: VCF file read with cyvcf2
    :return: 3d-array
    """
    vars = []
    arr = np.zeros((1, size, 2), dtype=int)
    for v in vcf_obj:
        vars.append(v.ID)
        arr = np.vstack((arr,
                         np.expand_dims(np.array(v.genotypes)[:, :-1],
                                        axis=0)))
    return arr[1:,:,:], vars


def vcf2dframe(vcf_obj, size):
    """
    Throws the genotypes values of a VCF file into an array.
    :param vcf_obj: VCF file read with cyvcf2
    :return: two dataframes, one for each allele of the genotype
    """
    vars = []
    arr = np.zeros((1, size, 2), dtype=int)
    for v in vcf_obj:
        vars.append(v.ID)
        arr = np.vstack((arr,
                         np.expand_dims(np.array(v.genotypes)[:, :-1],
                                        axis=0)))
    df0 = pd.DataFrame(arr[1:,:,0], index=vars, columns=vcf_obj.samples)
    df1 = pd.DataFrame(arr[1:, :, 1], index=vars, columns=vcf_obj.samples)
    return df0, df1


def get_maf(vcf_raw):
    subprocess.run(['''bcftools query -f '%ID\t%AF\n' {0} > {1}/TMP.maf.csv'''.format(vcf_raw, os.getcwd())],
                    shell=True,
                    cwd='/home/camilleclouard/PycharmProjects/1000Genomes/data/tests-beagle')
    df_maf = pd.read_csv('TMP.maf.csv',
                      sep='\t',
                      names=['id', 'maf'])
    df_maf.sort_values('id', axis=0, inplace=True)
    df_maf.reset_index(drop=True, inplace=True)
    df_maf.set_index('id', drop=False, inplace=True)
    df_maf['maf_inter'] = np.digitize(df_maf['maf'].astype(float),
                                      bins=np.array([0.00, 0.01, 0.05]))
    os.remove('TMP.maf.csv')
    return df_maf


def compute_imp_err(set_names, objs, raw, idx1, idx2, sorting):
    set_err = {}
    for k, dset in dict(zip(set_names, objs)).items():
        db = para_array(raw, dset)  # shape=(1000, 1992, 2, 2) OK
        print('Errors in {} dataset...'.format(k).ljust(80, '.'))
        single_errors = per_element_error(db, 0)
        df = pd.DataFrame(data=single_errors, index=idx1, columns=idx2)
        set_err[k] = {}
        set_err[k]['grid'] = df
        set_err[k]['mean'] = np.mean(single_errors)
        vsqr = np.vectorize(lambda x: np.power(x, 2))
        set_err[k]['log1p_mse'] = math.log1p(np.mean(vsqr(single_errors)))
        df.to_csv(k + '{}.csv'.format('.sorted' if sorting else ''),
                  sep='\t',
                  encoding='utf-8')
    return set_err


def tag_heteroz(arr):
    if np.isin(arr, 0).any() and np.isin(arr, 1).any():
        return True
    else:
        return False


def tag_missing(arr): # nan or -1?
    if np.sum(arr) == 2:
        return 2
    elif np.isin(arr, -1).any():
        return 1
    else:
        return 0


def minor_allele(arr):
    if np.sum(arr) == 2:
        return 2
    elif np.isin(arr, 1).any():
        return 1
    else:
        return 0


def per_site_heteroz(vcf_path):
    """

    :param vcf_obj:
    :return:
    """
    vcf_obj = VCF(vcf_path)
    dic_het = {}
    for var in vcf_obj:
        gt = np.array(var.genotypes)[:, :-1]
        dic_het[var.ID] = np.count_nonzero(np.apply_along_axis(tag_heteroz, 1, gt).astype(int))
    return dic_het


def count_missing_alleles(vcf_path):
    """

    :param vcf_obj:
    :return:
    """
    vcf_obj = VCF(vcf_path)
    dic_mis = {}
    for var in vcf_obj:
        gt = np.array(var.genotypes)[:, :-1]
        dic_mis[var.ID] = np.sum(np.apply_along_axis(tag_missing, 1, gt))#/(len(var.genotypes)*2) ?
    return dic_mis


def compute_maf(vcf_path, verbose=False):
    """

    :param vcf_obj:
    :return:
    """
    print('Computing MAFs from {}'.format(vcf_path).ljust(80, '.'))
    vcf_obj = VCF(vcf_path)
    dic_maf = {}
    for i, var in enumerate(vcf_obj):
        # GT:DS:GP
        if verbose:
            try:
                print(str(i) + '\t' + var.ID + '\t' + var.format('GP'))
            except:
                print(str(i) + '\t', var.ID)
        gt = np.array(var.genotypes)[:, :-1]
        dic_maf[var.ID] = np.sum(np.apply_along_axis(minor_allele, 1, gt))/(len(var.genotypes)*2)

    return dic_maf


def compute_maf_evol(set):
    """

    :param set: str, short name of the data set pooled/missing...
    :param df_maf: maf from the original vcf-chunked file, with markers ID as index
    :return:
    """
    print('Set --> ', set.upper())
    o = tw.read_queue(set)
    d = {**o[0], **o[1]}
    postimp_maf = d['postimp']
    preimp_maf = d['preimp']
    dic = dict()
    dic['preimp_' + set] = preimp_maf # caution, still missing data!
    dic['postimp_' + set] = postimp_maf
    return dic