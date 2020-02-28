from cyvcf2 import VCF, Writer
import pysam
import numpy as np
import pandas as pd
import subprocess
import collections
from scipy.stats import *
import math

import scripts.VCFPooling.poolSNPs.parameters as prm
from scripts.VCFPooling.poolSNPs import dataframe as vcfdf

from persotools.files import *

"""
Tools for manipulating and processing variants from VCF files.
"""


def tag_heteroz(arr):
    if np.isin(arr, 0).any() and np.isin(arr, 1).any():
        return 1
    else:
        return 0


def tag_missing(arr):
    if np.all(arr) == -1:
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


def per_site_sample_error(elem2x2):
    """
    Computes the imputation error as the distance between
    the true data set vs. imputed at one site for one sample.
    :param elem2x2: 2*2 array representing the pair of GTs to compare.
    Ex. 0|0  vs. 1|0 = [[0 0] [0 1]]
    :return: Z-norm. score for error: 0 = right, > 0 = wrong, max = 1
    """
    return np.array(abs(elem2x2[:2].sum() - elem2x2[2:].sum()))/2


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
    errors = np.apply_along_axis(per_site_sample_error, 1, arr2d)
    return errors.reshape(arr.shape[0], arr.shape[1])


def per_axis_error(arr4d, ax):
    """
       Cumulates error row- or column-wise
       :param arr4d: data sets to compare
       :param ax: axis over which to apply the cumulative sum
       :return: 1d-array of error values along the ax-axis
       """
    return per_element_error(arr4d, ax).sum(axis=1)/arr4d.shape[ax]


class VariantCallGenerator(object):
    """
    Generates single-type formatted calls of variants
    """

    def __init__(self, vcfpath: FilePath, format: str = None):
        """
        :param vcfpath:
        :param indextype: identifier for variants: 'id', 'chrom:pos'.
        Must be 'chrom:pos' if the input has been generated by Phaser
        """
        self.path = vcfpath
        self.fmt = format

    def __iter__(self):
        vcfobj = pysam.VariantFile(self.path)
        for var in vcfobj:
            yield [g[self.fmt] for g in var.samples.values()]


def convert_aaf(x: object):
    """
    Cast AAF as float or NaN
    :param x:
    :return:
    """
    try:
        x = float(x)
    except TypeError:
        x = np.nan
    finally:
        return x


def get_aaf(vcf_raw: str, idt: str = 'id') -> pd.DataFrame:
    #TODO: replace usages by PandasVCF instances in the whole code
    """
    Read the allele frequencies info field for all variants in a file.
    Return the computed alternate allele frequencies computed per variant from the input file.
    Variants must be GT filled in.
    :param vcf_raw: path to the VCF-formatted file with GT INFO fields
    :param idt: kind of ID wished for pandas.Index: 'id'|'chrom:pos̈́'
    :return: id-indexed dataframe with AF from INFO-field, computed AAF and binned AF_INFO
    """
    try:
        pandasvcf = vcfdf.PandasVCF(vcf_raw, indextype=idt)
        infoseries = pandasvcf.af_info
        aafseries = pandasvcf.aaf
        binseries = pandasvcf.aaf_binned(b=np.array([0.00, 0.01, 0.05]))
        df_aaf = pandasvcf.concatcols([infoseries, aafseries, binseries])
        df_aaf.sort_index(axis=0, inplace=True)

    except IOError or UnicodeDecodeError or MemoryError:
        if idt == 'id':
            subprocess.run(['''bcftools query -f '%ID\t%AF\n' {0} > {1}/TMP.aaf.csv'''.format(vcf_raw, os.getcwd())],
                           shell=True,
                           cwd=prm.DATA_PATH)
        if idt == 'chrom:pos':
            subprocess.run(['''bcftools query -f '%CHROM:%POS\t%AF\n' {0} > {1}/TMP.aaf.csv'''.format(vcf_raw, os.getcwd())],
                           shell=True,
                           cwd=prm.DATA_PATH)
        df_aaf = pd.read_csv('TMP.aaf.csv',
                             sep='\t',
                             names=['id', 'af_info'])
        os.remove('TMP.aaf.csv')

    return df_aaf


def compute_imp_err(set_names, objs, raw, idx1, idx2, sorting):
    # TODO: Something wrong in that function!!!
    set_err = {}
    for k, dset in dict(zip(set_names, objs)).items():
        db = para_array(raw, dset)
        print('Errors in {} dataset'.format(k).ljust(80, '.'))
        single_errors = per_element_error(db, 0)
        df = pd.DataFrame(data=single_errors, index=idx1, columns=idx2)
        set_err[k] = df
        df.to_csv(k + '{}.chunk{}.csv'.format('.sorted' if sorting else '', prm.CHK_SZ),
                  sep='\t',
                  encoding='utf-8')
    return set_err


def compute_discordance(setnames: list, objs: list, raw: str, idx1, idx2, sorting) -> dict:
    # TODO: refactor in metrics: trinary_encoding + diff (no account for phase here)
    """
    Compute discordance per variant per sample on input data sets.
    Trinary encoding is used for GT genotypes for avoiding 4d array
    :param setnames: names for dataframes: 'pooled'/'missing'
    :param objs: dataframes to evaluate
    :param raw: dataframe with ground truth genotype values
    :param idx1: lines index
    :param idx2: columns index
    :param sorting:
    :return:
    """
    set_err = {}
    for k, dset in dict(zip(setnames, objs)).items():
        # sum the 2 alleles
        raw_trinary = raw.sum(axis=-1)
        # print('\nraw_trinary: ', describe(raw_trinary))
        dset_trinary = dset.sum(axis=-1)
        # print('\ndset_trinary: ', describe(dset_trinary))
        # compare trinary genotypes: ground truth vs. computed
        mismatch = np.subtract(raw_trinary, dset_trinary)
        print('Discordance in {} dataset'.format(k).ljust(80, '.'))
        single_errors = np.absolute(mismatch) / 2
        # print('\nsingle_errors: ', describe(single_errors))
        # save discordance result to csv
        df = pd.DataFrame(data=single_errors, index=idx1, columns=idx2)
        set_err[k] = df
        df.to_csv(k + '{}.chunk{}.csv'.format('.sorted' if sorting else '', prm.CHK_SZ),
                  sep='\t',
                  encoding='utf-8')
    return set_err


def count_missing_alleles(vcf_path=None, gt_array=None, id='id'):
    #TODO: find usages and replace with PandasVCF.missing_rate
    """

    :param vcf_obj:
    :return:
    """
    dic_mis = collections.OrderedDict()

    if vcf_path is not None and gt_array is not None:
        raise ValueError

    elif vcf_path is None and gt_array is None:
        mis = None

    elif vcf_path is not None:
        vcf_obj = VCF(vcf_path)
        for var in vcf_obj:
            gt = np.array(var.genotypes)[:, :-1]
            if id == 'id':
                dic_mis[var.ID] = np.sum(
                    np.apply_along_axis(
                        tag_missing, -1, gt)
                )/(len(var.genotypes)*2)
            if id == 'chrom:pos':
                dic_mis['{}:{}'.format(var.CHROM, var.POS)] = np.sum(
                    np.apply_along_axis(
                        tag_missing, -1, gt)
                )/(len(var.genotypes)*2)
        mis = np.asarray([[k, v] for k, v in dic_mis.items()])

    else:
        tag = np.apply_along_axis(
            tag_missing, -1, gt_array[:, :, :-1]
        ).astype(int)
        mis = np.apply_along_axis(np.sum, 0, tag)

    return mis


def compute_zygosity_evol(zygosity: str, idt: str = 'id') -> list:
    pass


def rmse_df(df, kind='rmse', ax=None, lev=None):
    df.astype(float, copy=False)
    sqr = df.applymap(lambda x: np.power(x, 2))
    if ax is None: # rmse overall
        mse = np.mean(sqr.values)
        rmse = math.sqrt(mse)
    else: # rmse per marker/per sample
        mse = sqr.mean(axis=ax, level=lev)
        rmse = mse.apply(math.sqrt).rename('rmse')
    if kind == 'rmse':
        return rmse
    else:
        return mse


def extract_variant_onfreq(file_in: FilePath, aaf_range: list) -> pd.DataFrame:
    """
    Returns variants where the alternate allele has a frequency
    in the input range.
    :param file_in: VCF-formatted file
    :param aaf_range: list: [min, max] of the range the AAF should be comprised in.
    :return: dataframe of cyvcf2.Variants
    """
    pdvcf = vcfdf.PandasVCF(file_in, idt='chrom:pos')
    dfaaf = pdvcf.concatcols([pdvcf.af_info, pdvcf.aaf])
    inf, sup = aaf_range[0], aaf_range[1]
    #extracted = aafs.loc[(aafs['af_info'] >= min and aafs['af_info'] <= max).all()]
    extracted = dfaaf.query('af_info >= @inf & af_info <= @sup')

    return extracted


def map_gt_gl(arr_in, unknown=[1/3, 1/3, 1/3]):
    gt = arr_in[:-1]
    if 0 in gt and 1 in gt:
        gl = np.array([0.0, 1.0, 0.0])
    elif 1 in gt and -1 not in gt:
        gl = np.array([0.0, 0.0, 1.0])
    elif 0 in gt and -1 not in gt:
        gl = np.array([1.0, 0.0, 0.0])
    elif -1 in gt and 1 in gt:
        gl = np.array([0.0, 0.5, 0.5])
    elif -1 in gt and 0 in gt:
        gl = np.array([0.5, 0.5, 0.0])
    else: # np.nan, np.nan OR -1, -1 ?
        gl = np.array(unknown)
    return gl


def repr_gl_array(arr):
    arr2str = np.vectorize(lambda x: "%.5f" % x)
    arr_str = np.apply_along_axis(lambda x: ','.join(arr2str(x)),
                                  axis=-1,
                                  arr=arr)
    strg = np.apply_along_axis(lambda x: '\t'.join(x),
                               axis=0,
                               arr=np.asarray(arr_str.squeeze()))
    return strg


def bin_loggl_converter(v_in):
    # v_in: cyvcf2 variant
    g_in = v_in.genotypes
    g_out = np.apply_along_axis(map_gt_gl, 1, g_in)
    logzero = np.vectorize(lambda x: -5.0 if x <= pow(10, -5) else math.log10(x))
    # Beagles needs log-GL
    g_out = logzero(g_out)
    return g_out


def bin_gl_converter(v_in):
    # v_in: cyvcf2 variant
    g_in = v_in.genotypes
    g_out = np.apply_along_axis(map_gt_gl, 1, g_in)
    return g_out


def fmt_gl_variant(v_in, glfunc=bin_loggl_converter):
    info = ';'.join([kv for kv in ['='.join([str(k), str(v)]) for k, v in v_in.INFO]])
    gl = repr_gl_array(np.array(list(map(glfunc, [v_in]))))
    toshow = np.asarray([v_in.CHROM,
                         v_in.POS,
                         v_in.ID,
                         ''.join(v_in.REF),
                         ''.join(v_in.ALT),
                         v_in.QUAL if not None else '.',
                         'PASS' if v_in.FILTER is None else v_in.FILTER,
                         info,
                         'GL',
                         gl],
                        dtype=str)
    towrite = '\t'.join(toshow) + '\n'
    return towrite


def file_likelihood_converter(f_in, f_out, func=bin_loggl_converter):
    """
    output shoulb written as uncom,pressed vcf!
    """
    str_header = '##FORMAT=<ID=GL,Number=G,Type=Float,Description="three log10-scaled likelihoods for RR,RA,AA genotypes">'
    dic_header = {'ID': 'GL',
                  'Number': 'G',
                  'Type': 'Float',
                  'Description': 'three log10-scaled likelihoods for RR,RA,AA genotypes'}
    vcf_in = VCF(f_in)
    vcf_in.add_format_to_header(dic_header)

    for lin in vcf_in.header_iter():
        try:
            lin['ID'] == 'GT'
            del lin
        except KeyError:
            pass

    print('Writing metadata of {}'.format(f_out).ljust(80, '.'))
    w1 = Writer(f_out, vcf_in)
    w1.write_header()
    w1.close()

    print('Writing data in {}'.format(f_out).ljust(80, '.'))
    with open(f_out, 'ab') as w2:
        for var_in in vcf_in:
            stream = fmt_gl_variant(var_in, glfunc=func).encode()
            w2.write(stream)


def get_pop():
    df_pop = pd.read_csv(os.path.join(prm.DATA_PATH, '20130606_sample_info.csv'),
                         sep=',',
                         header=0,
                         usecols=[0, 1])
    df_pop.sort_values(['Sample', 'Population'], axis=0, inplace=True)
    return df_pop


def make_index(raw_data, src=None, idt='id'):
    if src is None:
        src = os.path.join(prm.PATH_GT_FILES, prm.CHKFILE)
    group = get_pop()
    pdvcf = vcfdf.PandasVCF(src, indextype=idt)
    df_aaf = pdvcf.af_info.to_frame().reset_index()

    samples = pd.Series(VCF(raw_data).samples,
                        name='Sample').str.rstrip('_IMP').to_frame()
    df_pop = group.merge(samples, on='Sample', how='inner')

    aaf_idx = pd.MultiIndex.from_arrays(list(zip(*df_aaf.values)), names=['id', 'af_info'])
    pop_idx = pd.MultiIndex.from_arrays(list(zip(*df_pop.values)), names=['Sample', 'Population'])

    return aaf_idx, pop_idx


if __name__ == '__main__':
    prm.info()  # print config infos

    # create GL encoded file from raw GT
    vcfin = '/home/camille/1000Genomes/data/gt/stratified/IMP.chr20.snps.gt.chunk10000.vcf.gz'
    vcfout = '/home/camille/1000Genomes/data/gl/IMP.chr20.snps.gl.chunk10000.vcf'
    file_likelihood_converter(vcfin, vcfout, func=bin_gl_converter)  # easier for cross entropies not to log gl

    os.chdir('/home/camille/1000Genomes/data/gl/gl_adaptive/all_snps_all_samples')
    fpath = 'IMP.chr20.pooled.beagle2.gl.chunk10000.vcf.gz'
    mydf = vcfdf.PandasMixedVCF(fpath)

