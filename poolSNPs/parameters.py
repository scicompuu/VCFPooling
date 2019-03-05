#!/usr/bin/env python
"""
Parameters for running pooling + decoding on a dataset:
- path to file to process
- make new directory if needed: today's date, split data and pictures?
- files names/extension for outputs
- iteration number missing/pooled/missing.pooled
- chunks size if needed
"""

import os
from cyvcf2 import VCF

global DATA_PATH, PLOTS_PATH
global CHK_SZ, SOURCE, KIND, MSS, POOL, WD
global RAW, POOLED, MISSING, MISS_POOL

### GENERAL TOOLS

def pgcd(a, b):
    """pgcd(a,b): calcul du 'Plus Grand Commun Diviseur' entre les 2 nombres entiers a et b"""
    while b != 0:
        r = a % b
        a, b = b, r
    return a


def ppcm(a, b):
    """ppcm(a,b): calcul du 'Plus Petit Commun Multiple' entre 2 nombres entiers a et b"""
    if (a == 0) or (b == 0):
        return 0
    else:
        return (a*b)//pgcd(a, b)


### all
DATA_PATH = '/home/camille/PycharmProjects/1000Genomes/data'
PLOTS_PATH = '/home/camille/PycharmProjects/1000Genomes/plots'


### pool.py
WD = os.path.join(DATA_PATH, 'tests-beagle')
CHK_SZ = 10000
SUBCHUNK = 1000
PATH_IN = 'ALL.chr20.snps.gt.vcf.gz'
PATH_OUT = ['ALL.chr20.pooled.snps.gt.chunk{}.vcf'.format(str(CHK_SZ)),
            'ALL.chr20.missing.snps.gt.chunk{}.vcf'.format(str(CHK_SZ))]
#'ALL.chr20.pooled.missing.snps.gt.chunk{}.vcf'.format(str(CHK_SZ)),

KIND = 'gt'
MSS = [False, True]
POOL = [True, False]
SOURCE = 'ALL.chr20.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ))


### beagle.py
RAW = {'vcf':'ALL.chr20.snps.gt.chunk{}.vcf'.format(str(CHK_SZ)),
       'gz':'ALL.chr20.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
       'ref': 'REF.chr20.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
       'imp': 'IMP.chr20.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
       'b1r':'REF.chr20.beagle1.chunk{}'.format(str(CHK_SZ)),
       'b1i':'IMP.chr20.beagle1.chunk{}'.format(str(CHK_SZ))}

POOLED = {'vcf':'ALL.chr20.pooled.snps.gt.chunk{}.vcf'.format(str(CHK_SZ)),
          'gz':'ALL.chr20.pooled.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
          'imp': 'IMP.chr20.pooled.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
          'b1':'IMP.chr20.pooled.beagle1.chunk{}'.format(str(CHK_SZ)),
          'b2':'IMP.chr20.pooled.beagle2.chunk{}'.format(str(CHK_SZ)),
          'corr':'IMP.chr20.pooled.beagle2.chunk{}.corr'.format(str(CHK_SZ)),
          'cfgt': 'IMP.chr20.pooled.cfgt.chunk{}'.format(str(CHK_SZ))}

MISSING = {'vcf':'ALL.chr20.missing.snps.gt.chunk{}.vcf'.format(str(CHK_SZ)),
           'gz':'ALL.chr20.missing.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
           'imp': 'IMP.chr20.missing.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
           'b1':'IMP.chr20.missing.beagle1.chunk{}'.format(str(CHK_SZ)),
           'b2':'IMP.chr20.missing.beagle2.chunk{}'.format(str(CHK_SZ)),
           'corr': 'IMP.chr20.missing.beagle2.chunk{}.corr'.format(str(CHK_SZ)),
           'cfgt': 'IMP.chr20.missing.cfgt.chunk{}'.format(str(CHK_SZ))}

MISS_POOL = {'vcf':'ALL.chr20.missing.snps.gt.chunk{}.vcf'.format(str(CHK_SZ)),
             'gz':'ALL.chr20.missing.pooled.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
             'imp': 'IMP.chr20.missing.pooled.snps.gt.chunk{}.vcf.gz'.format(str(CHK_SZ)),
             'b1':'IMP.chr20.missing.pooled.beagle1.chunk{}'.format(str(CHK_SZ)),
             'b2':'IMP.chr20.missing.pooled.beagle2.chunk{}'.format(str(CHK_SZ)),
             'corr': 'IMP.chr20.missing.pooled.beagle2.chunk{}.corr'.format(str(CHK_SZ)),
             'cfgt': 'IMP.chr20.missing.pooled.cfgt.chunk{}'.format(str(CHK_SZ))}

nb_samples = len(VCF(os.path.join(WD, RAW['gz'])).samples)
pools_size = 16
pools_imp = ppcm(nb_samples, pools_size) // (10 * pools_size)
NB_IMP = pools_imp * pools_size
NB_REF = nb_samples - NB_IMP
print(nb_samples, pools_imp)
