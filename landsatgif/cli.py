#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import click

import numpy as np


import time
import uuid

import rasterio as rio
from rasterio import transform
from rasterio.enums import Resampling
from rasterio.io import VirtualWarpedFile

from matplotlib import cm

from PIL import Image, ImageFont, ImageDraw

from landsatgif import __version__ as landsatgif_version
from landsatgif import utils
from landsatgif import images2gif


font = ImageFont.load_default().font

@click.group()
@click.version_option(version=landsatgif_version, message='%(version)s')
def main():
    pass

@main.command()
@click.option('--lat', type=float, required=True,
    help='Latitude of the query, between 90 and -90.')
@click.option('--lon', type=float, required=True,
    help='Longitude of the query, between 180 and -180.')
@click.option(
    '--cloud', '-c', type=float, default=20.,
    help='Maximum cloud percentage (%) allowed.')
@click.option(
    '--start_date', '-s', type=str, default='2013-01-01',
    help='Start date of the query in the format YYYY-MM-DD.')
@click.option(
    '--end_date', '-e', type=str, default=time.strftime('%Y-%m-%d'),
    help='End date of the query in the format YYYY-MM-DD.')

@click.option(
    '--res', type=int, default=30,
    help='Output Resolution')

@click.option(
    '--buffer_size', '-b', type=int, default=10000,
    help='Buffer size around lat/lon point for image creation. (in meters)')
@click.option(
    '--ndvi', is_flag=True,
    help='Create NDVI animation instead of RGB')

@click.option(
    '--output', '-o', type=str, default='./{}.gif'.format(str(uuid.uuid1())),
    help='output filename')

def main(lat, lon, cloud, start_date, end_date, buffer_size, res, ndvi, output):
    """ Create animated GIF from landsat 8 data"""

    aoi_wgs84 = utils.lonlat_to_geojson(lon, lat, buffer_size)
    results = utils.sat_api_search(aoi_wgs84, 'landsat', start_date, end_date, cloud)

    click.echo('{} scenes found'.format(len(results)))

    scenes_params = list(map(utils.landsat_parse_scene_id, results))
    # filter same date image

    # #Check Only if ROW is the same (same date)
    # all_pr = ['{:03d},{:03d}'.format(int(i['path']),int(i['row'])) for i in proc_images]
    # all_row = [i['row'] for i in proc_images]
    # if len(list(set(all_row))) > 1:
    #     print '''AOI covering more than one Row :
    #     Please choose one of the following: {}
    #     Using --path_row option'''.format(' | '.join(list(set(all_pr))))
    #     sys.exit(1)

    #Output transform
    aoi_bounds = utils.feat_to_bounds(aoi_wgs84) # (minx, miny, maxx, maxy)

    width = int((aoi_bounds[2] - aoi_bounds[0]) / float(res))
    height = int((aoi_bounds[3] - aoi_bounds[1]) / float(res))

    dst_affine = transform.from_bounds(*aoi_bounds, width, height)

    l8_images = []
    for scene in scenes_params:

        landsat_address = 's3://landsat-pds/{}'.format(scene['key'])

        if ndvi:

            meta_data = utils.landsat_get_mtl(scene['scene'])

            band_address = '{}_B4.TIF'.format(landsat_address)
            with VirtualWarpedFile(band_address,
                dst_crs='EPSG:3857',
                resampling=Resampling.bilinear).open() as src:

                window = src.window(*aoi_bounds, boundless=True)
                matrix = src.read(window=window,
                    out_shape=(height, width), indexes=1,
                    resampling=Resampling.bilinear, boundless=True)

                b4 = utils.landsat_to_toa(matrix, 4, meta_data)

            band_address = '{}_B5.TIF'.format(landsat_address)
            with VirtualWarpedFile(band_address,
                dst_crs='EPSG:3857',
                resampling=Resampling.bilinear).open() as src:

                window = src.window(*aoi_bounds, boundless=True)
                matrix = src.read(window=window,
                    out_shape=(height, width), indexes=1,
                    resampling=Resampling.bilinear, boundless=True)

                b5 = utils.landsat_to_toa(matrix, 5, meta_data)

            ratio = np.where( b5 * b4 > 0, np.nan_to_num((b5 - b4) / (b5 + b4)), 0)

            #Use winter colormap (http://matplotlib.org/examples/color/colormaps_reference.html)
            img = Image.fromarray(np.uint8(cm.winter((ratio + 1.) / 2.) * 255)).convert('RGB')
            draw = ImageDraw.Draw(img)
            xs,ys = draw.textsize(scene['date'],  font=font)
            draw.rectangle([ (5, 5), (xs+15, ys+15) ], fill=(255,255,255))
            draw.text((10, 10), scene['date'], (0,0,0), font=font)
            l8_images.append(img)
            
        else:

            out = np.zeros((3, height, width), dtype=np.uint8)

            rgb = [4, 3, 2]
            for b in range(len(rgb)):
                band_address = '{}_B{}.TIF'.format(landsat_address, rgb[b])

                with VirtualWarpedFile(band_address,
                    dst_crs='EPSG:3857',
                    resampling=Resampling.bilinear).open() as src:

                    window = src.window(*aoi_bounds, boundless=True)
                    matrix = src.read(window=window,
                        out_shape=(height, width), indexes=1,
                        resampling=Resampling.bilinear, boundless=True)

                    p2, p98 = np.percentile(matrix[matrix > 0], (2, 98))
                    matrix = np.where(matrix > 0,
                        utils.linear_rescale(matrix,
                        in_range=[int(p2), int(p98)], out_range=[1, 255]), 0)

                    out[b] = matrix.astype(np.uint8)

            img = Image.fromarray(np.dstack(out))
            draw = ImageDraw.Draw(img)
            xs,ys = draw.textsize(scene['date'],  font=font)
            draw.rectangle([ (5, 5), (xs+15, ys+15) ], fill=(255,255,255))
            draw.text((10, 10), scene['date'], (0,0,0), font=font)
            l8_images.append(img)

    #
    # if len(l8_images) > 0:
    #     images2gif.writeGif(output, l8_images, duration=0.5, dither=0)
