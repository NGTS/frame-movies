#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division, print_function, absolute_import

import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import multiprocessing as mp
import multiprocessing.dummy as threadmp
import bz2
import tempfile
from contextlib import contextmanager
from functools import partial
import subprocess as sp
from astropy.io import fits
import shutil
import sys
import numpy as np
import logging

logging.basicConfig(level='INFO', format='%(levelname)10s - %(message)s')
logger = logging.getLogger(__file__)

mplogger = mp.log_to_stderr()
mplogger.setLevel('WARNING')

ALLOWED_RESIZE_FACTORS = {2, 4, 8}


@contextmanager
def open_fits_file(filename):
    if filename.endswith('.bz2'):
        with bz2.BZ2File(filename) as uncompressed:
            with fits.open(uncompressed) as infile:
                yield infile
    else:
        with fits.open(filename) as infile:
            yield infile


def getheader(filename, hdu=0):
    with open_fits_file(filename) as infile:
        return infile[hdu].header


def getdata(filename, hdu=0):
    with open_fits_file(filename) as infile:
        return infile[hdu].data


class NullPool(object):
    '''
    Null object pattern for a ``multiprocessing.Pool`` object, when
    multiprocessing is not used. Provides the same interface.
    '''

    def __init__(self, *args, **kwargs):
        pass

    def map(self, fn, args):
        return map(fn, args)


def rebin(a, shape, total=True):
    '''
    Image rebinning routine
    http://stackoverflow.com/a/8090605/56711
    '''
    sh = shape[0], a.shape[0] // shape[0], shape[1], a.shape[1] // shape[1]
    if total:
        fn = np.sum
    else:
        fn = np.mean
    return fn(fn(a.reshape(sh), axis=-1), axis=1)


def pack_images(dirname, output_name, kind='png'):
    '''
    Compress the png images for easy copying.

    :param dirname:
        Directory where the png images are contained

    :param output_name:
        Resulting tarball name

    :param kind:
        Search for this kind of image

    .. deprecated::
    '''
    full_out_path = os.path.realpath(output_name)
    with change_directory(dirname):
        cmd = ['tar', 'czf', full_out_path]
        cmd.extend([fname for fname in os.listdir('.') if '.png' in fname])
        str_cmd = map(str, cmd)
        logger.debug("Running command [{}]".format(' '.join(str_cmd)))
        sp.check_call(str_cmd)


def construct_output_filename(outdir, input_fname, i, include_increment=True):
    basename = os.path.basename(input_fname)
    if include_increment:
        stub = '{:05d}_{}.png'.format(i, basename)
    else:
        stub = '{}.png'.format(basename)

    return os.path.join(outdir, stub)


def extract_image_data(input_fname):
    '''
    Given a fits image, extract the image data and header.

    If the image is raw (has an extra 40 columns), compute the overscan and
    remove first before returning the image.

    :param input_fname:
        Input filename
    '''
    with open_fits_file(input_fname) as infile:
        image_data = infile[0].data
        header = infile[0].header

    if image_data.shape == (2048, 2088):
        overscan = image_data[4:, -15:].mean()
        logger.debug('Image is raw, subtracting overscan {}'.format(overscan))
        image_data = image_data[:, 20:-20] - overscan

    return header, image_data


def build_image(inp, outdir, median_behaviour,
                frame_min=0.8,
                frame_max=1.2,
                nimages=None,
                resize_factor=None,
                include_increment=True):
    '''
    Given a file, render a png of the output to the ``outdir`` directory.

    :param i:
        Incrementing integer counter to keep the images in order

    :param input_fname:
        Filename

    :param outdir:
        Output directory for the png file

    :param median_behaviour:
        Time series object for rendering the median time series

    :param frame_min:
        Multiple of the median to set the lower value for the colour scale

    :param frame_max:
        Multiple of the median to set the upper value for the colour scale

    :param resize_factor:
        Downsample the images by this factor before rendering the png

    :param nimages:
        Number of images in the complete set
    '''
    i, input_fname = inp
    output_fname = construct_output_filename(outdir, input_fname, i,
                                             include_increment=include_increment)
    if nimages is None:
        logger.info('Building image %s', i + 1)
    else:
        logger.info('Building image %s/%s', i + 1, nimages)

    logger.debug('%s => %s', input_fname, output_fname)

    if os.path.isfile(output_fname):
        logger.debug("Image {} exists, skipping".format(output_fname))
        return

    no_time_series = median_behaviour is None
    fig = plt.figure(figsize=(8, 8))

    if no_time_series:
        axes = [fig.add_subplot(111),]
    else:
        # Get around not having plt.subplots in matplotlib versions < 1.4
        axes = [plt.subplot2grid((4, 4), (0, 0),
                                 colspan=3,
                                 rowspan=3),
                plt.subplot2grid((4, 4), (3, 0),
                                 colspan=3),]

    header, image_data = extract_image_data(input_fname)

    if resize_factor is not None:
        if resize_factor not in ALLOWED_RESIZE_FACTORS:
            raise RuntimeError("Invalid resize factor given, allowed: {allowed}".format(
                allowed=ALLOWED_RESIZE_FACTORS))
        new_shape = (image_data.shape[0] // resize_factor, image_data.shape[1] //
                     resize_factor)
        image_data = rebin(image_data, new_shape)

    med_image = np.median(image_data)
    z1, z2 = (med_image * frame_min, med_image * frame_max)
    if z1 > z2:
        z1, z2 = z2, z1

    axes[0].imshow(image_data,
                   interpolation='None',
                   origin='lower',
                   cmap=plt.cm.afmhot,
                   vmin=z1,
                   vmax=z2)
    for dimension in ['xaxis', 'yaxis']:
        getattr(axes[0], dimension).set_visible(False)
    axes[0].set_title(header.get('image_id', None))

    if not no_time_series:
        median_behaviour.plot(axes[1])
        median_behaviour.add_vline(axes[1], i)

    fig.tight_layout()
    fig.savefig(output_fname, bbox_inches='tight')
    plt.close(fig)


def sort_images(images):
    '''
    Sort images by mjd

    :param images:
        List of images to sort
    '''
    logger.info('Sorting images by mjd')
    return sorted(images, key=lambda fname: getheader(fname)['mjd'])


def generate_movie(image_directory, output_filename, fps=15, use_mencoder=False):
    '''
    Render a mp4 movie from a directory of png files. Use ffmpeg for this.

    :param image_directory:
        Directory of png files

    :param output_filename:
        Resulting movie filename

    :param fps:
        Frames per second of the final movie

    :param use_mencoder:
        Use mencoder instead of ffmpeg
    '''
    output_filename = os.path.realpath(output_filename)

    logger.info('Building movie file {}, fps {}'.format(output_filename, fps))
    n_cpu = mp.cpu_count()
    with change_directory(image_directory):
        if use_mencoder:
            cmd = list(map(str, [
                'mencoder', 'mf://*.png', '-mf',
                'w=800:h=600:fps={}:type=png'.format(fps), '-ovc', 'x264',
                '-x264encopts',
                'crf=18:nofast_pskip:nodct_decimate:nocabac:global_header:threads={}'.format(
                    n_cpu), '-of', 'lavf', '-lavfopts', 'format=mp4', '-o',
                output_filename
            ]))
        else:
            cmd = list(map(str, ['ffmpeg', '-y', '-framerate', fps, '-pattern_type',
                                 'glob', '-i', '*.png', '-c:v', 'mpeg4', '-b:v', '16M',
                                 '-threads', n_cpu, output_filename]))

        logger.debug('Running command %s', ' '.join(cmd))
        sp.check_call(cmd)


def ensure_dir(d, clobber=True):
    '''
    Ensure a directory is present by attempting to make it, then removing and
    trying again if an error occurs
    '''
    if os.path.isdir(d):
        if clobber:
            shutil.rmtree(d)
            os.makedirs(d)
    else:
        os.makedirs(d)


@contextmanager
def temporary_directory(images_dir=None, delete=True, clobber=True, *args, **kwargs):
    '''
    Create either a temporary directory which is removed after use, or ensuring
    a custom directory exists if passed. Args and kwargs are passed on to
    ``tempfile.mkdtemp``.

    :param images_dir:
        If ``None``, create a temporary directory, otherwise is a directory
        name

    :param delete:
        If temporary directory is created, delete it when finished?
    '''
    if images_dir is not None:
        ensure_dir(images_dir, clobber=clobber)
        yield images_dir
    else:
        dirname = tempfile.mkdtemp(*args, **kwargs)
        try:
            yield dirname
        finally:
            if delete:
                shutil.rmtree(dirname)


@contextmanager
def change_directory(path):
    '''
    Context manager to change into a directory, then back again when the scope
    is over

    :param path:
        New path to change to
    '''
    old_cwd = os.getcwd()
    try:
        logger.debug("Changing directory to {}".format(path))
        os.chdir(path)
        yield path
    finally:
        os.chdir(old_cwd)


def _extract(fname):
    '''
    Extract the mjd and median of each image
    '''
    header, image_data = extract_image_data(fname)
    med_image = np.median(image_data)
    return header['mjd'], med_image


class TimeSeries(object):
    '''
    Object to store a time series, and plot itself.
    '''

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.mjd0 = int(self.x.min())
        self.x -= self.mjd0

    @classmethod
    def extract_from(cls, files):
        '''
        Build a ``TimeSeries`` object from a series of fits files.
        '''
        pool = threadmp.Pool()

        x, y = map(np.array, zip(*pool.map(_extract, files)))
        ind = x.argsort()
        return cls(x[ind], y[ind])

    @property
    def ylims(self):
        '''
        Return the quartiles
        '''
        return np.percentile(self.y, [2.5, 97.5])

    def plot(self, axis):
        axis.plot(self.x, self.y, '.')
        axis.set_ylim(*self.ylims)
        axis.set_xlabel('MJD - {}'.format(self.mjd0))
        axis.set_ylabel(r'Image median / ADU')

    def add_vline(self, axis, index):
        axis.axvline(self.x[index], color='k', ls='--')


def create_movie(files,
                 output_movie=None,
                 images_directory=None,
                 delete_tempdir=True,
                 sort=True,
                 multiprocess=True,
                 fps=15,
                 use_mencoder=False,
                 no_time_series=False,
                 clobber_images_directory=True,
                 resize_factor=None,
                 include_increment=True,
                 verbose=False):
    '''
    Build a movie out of a series of fits files.

    :param files:
        Files to render

    :param output_movie:
        Resulting filename for the movie. If not given then do not render
        a movie

    :param images_directory:
        Directory to put the png files. If not supplied use a random temporary
        directory, and delete after use. Otherwise leave the specified
        directory in place

    :param delete_tempdir:
        If using a temporary png directory, delete it after the movie is
        finished

    :param sort:
        Sort by the fits header keyword ``mjd``

    :param multiprocess:
        Generate the png movies in parallel

    :param fps:
        Frames per second of the final movie

    :param resize_factor:
        Downsample the images by this factor before rendering the png

    :param verbose:
        Print more verbose logging information
    '''

    if verbose:
        logger.setLevel('DEBUG')

    logger.info('Building {} files'.format(len(files)))

    if len(files) == 0:
        logger.warning('No files to build')
        return

    if output_movie is None:
        logger.warning('Not creating movie')

    with temporary_directory(images_directory,
                             clobber=clobber_images_directory,
                             delete=delete_tempdir) as image_dir:

        logger.info("Building into {}".format(image_dir))

        if sort:
            sorted_files = sort_images(files)
        else:
            logger.warning('Not sorting images')
            sorted_files = files

        logger.info('Extracting time series from data')
        if not no_time_series:
            median_behaviour = TimeSeries.extract_from(sorted_files)

        else:
            median_behaviour = None

        logger.info('Building movie images')
        pool = mp.Pool() if multiprocess else NullPool()
        fn = partial(build_image,
                     outdir=image_dir,
                     median_behaviour=median_behaviour,
                     include_increment=include_increment,
                     resize_factor=resize_factor,
                     nimages=len(sorted_files))
        pool.map(fn, enumerate(sorted_files))

        if output_movie is not None:
            output_filename = os.path.realpath(output_movie)
            generate_movie(image_dir, output_filename,
                           fps=fps,
                           use_mencoder=use_mencoder)


def main(args):
    '''
    Main script access when calling from the command line. Just take
    the arguments object from argparse and convert to function arguments
    '''
    create_movie(files=args.filename,
                 output_movie=args.output,
                 images_directory=args.images_dir,
                 sort=not args.no_sort,
                 multiprocess=not args.no_multiprocessing,
                 delete_tempdir=not args.no_delete_tmpdir,
                 use_mencoder=args.use_mencoder,
                 no_time_series=args.no_time_series,
                 include_increment=not args.no_include_increment,
                 clobber_images_directory=not args.no_clobber_images_dir,
                 resize_factor=args.resize,
                 verbose=args.verbose,)


def parse_args():
    '''
    Use argparse to parse the command line arguments and pass to the main
    function
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', nargs='+')
    parser.add_argument('-o', '--output', help="Output movie name", required=False)
    parser.add_argument('--no-sort',
                        action='store_true',
                        default=False,
                        help='Do not sort by mjd')
    parser.add_argument('-f', '--fps',
                        help='Frames per second',
                        required=False,
                        default=15,
                        type=int)
    parser.add_argument('--no-multiprocessing',
                        help='Run serially',
                        action='store_true',
                        default=False)
    parser.add_argument('-d', '--images-dir',
                        required=False,
                        help='Custom directory to put the intermediate images')
    parser.add_argument('--no-delete-tmpdir',
                        action='store_true',
                        default=False,
                        help='Do not delete temporary directory of pngs')
    parser.add_argument('--use-mencoder',
                        action='store_true',
                        default=False,
                        help='Use mencoder instead of ffmpeg')
    parser.add_argument('--verbose',
                        action='store_true',
                        default=False,
                        help='Verbose logging')
    parser.add_argument('-T', '--no-time-series',
                        action='store_true',
                        default=False,
                        help='Disable time series plot')
    parser.add_argument('-I', '--no-include-increment',
                        default=False,
                        action='store_true',
                        help='Disable increment counter in output filename')
    parser.add_argument('-C', '--no-clobber-images-dir',
                        default=False,
                        action='store_true',
                        help='Do not overwrite images directory')
    parser.add_argument('-r', '--resize',
                        help='Resize images before rendering',
                        type=int,
                        choices=sorted(list(ALLOWED_RESIZE_FACTORS)),
                        required=False)
    return parser.parse_args()


if __name__ == '__main__':
    main(parse_args())
