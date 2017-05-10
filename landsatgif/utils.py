#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import json
import math
import numpy as np
import click
import requests
import datetime

from functools import partial

import pyproj
from shapely.ops import transform
from shapely.geometry import mapping, shape, Point

try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen

################################################################################
def lonlat_to_geojson(lon, lat, buff_size):
    '''
    Create GeoJSON feature collection from Lat Lon
    '''
    geom = Point(lon, lat)

    if buff_size:
        to_web_mercator = partial(
            pyproj.transform,
            pyproj.Proj(init='epsg:4326'),
            pyproj.Proj(init='epsg:3857'))

        to_wgs84 = partial(
            pyproj.transform,
            pyproj.Proj(init='epsg:3857'),
            pyproj.Proj(init='epsg:4326'))

        point_wm = transform(to_web_mercator, geom)
        geom = point_wm.buffer(buff_size, cap_style=3)
        geom = transform(to_wgs84, geom)

    return json.dumps(mapping(geom))

def feat_to_bounds(geom, crs='epsg:3857'):
    '''
    Create GeoJSON feature collection from Lat Lon
    '''
    geom = shape(json.loads(geom))

    project = partial(
        pyproj.transform,
        pyproj.Proj(init='epsg:4326'),
        pyproj.Proj(init=crs))

    geom = transform(project, geom)

    return geom.bounds

################################################################################
def sat_api_search(geom, sat, start_date, end_date, cloud):
    '''
    Call sat-api to search Satellites metadata
    '''

    sat_api_url = 'https://api.developmentseed.org/satellites/'

    try:
        params = {
            'intersects': geom,
            'satellite_name': sat,
            'date_from': start_date,
            'date_to': end_date,
            'cloud_from': 0,
            'cloud_to': cloud,
            'limit': 1000
        }

        r = requests.post(sat_api_url, json=params, headers={'Content-Type': 'application/json'})

        return [ x['scene_id'] for x in r.json()['results'] ]

    except:
        raise click.ClickException('Error while call sat-api')


################################################################################
def landsat_get_mtl(sceneid):
    '''
    Get Landsat MTL metadata
    '''

    try:
        scene_params = landsat_parse_scene_id(sceneid)
        meta_file = 'http://landsat-pds.s3.amazonaws.com/{}_MTL.txt'.format(scene_params['key'])

        return urlopen(meta_file).readlines()

    except:
        raise click.ClickException('Could not retrieve {} metadata'.format(sceneid))

################################################################################
def landsat_mtl_extract(meta, param):
    '''
    Parse Landsat MTL metadata
    '''

    for line in meta:
        data = line.decode().split(' = ')
        if (data[0]).strip() == param:
            return (data[1]).strip()

################################################################################
def landsat_to_toa(dn, nband, mfile):
    '''
    Conversion to Top Of Atmosphere planetary reflectance
    Ref: http://landsat.usgs.gov/Landsat8_Using_Product.php
    '''

    Mp = float(landsat_mtl_extract(mfile, 'REFLECTANCE_MULT_BAND_{}'.format(nband)))
    Ap = float(landsat_mtl_extract(mfile, 'REFLECTANCE_ADD_BAND_{}'.format(nband)))
    SE = math.radians(float(landsat_mtl_extract(mfile, 'SUN_ELEVATION')))

    return np.where(dn > 0, ((Mp*dn + Ap) / math.sin(SE) * 10000).astype(np.uint16), 0)

################################################################################
def landsat_parse_scene_id(sceneid):
    '''
    Author @perrygeo - http://www.perrygeo.com

    parse scene id
    '''

    if not re.match('^(L[COTEM]8\d{6}\d{7}[A-Z]{3}\d{2})|(L[COTEM]08_L\d{1}[A-Z]{2}_\d{6}_\d{8}_\d{8}_\d{2}_T1)$', sceneid):
        raise ValueError('Could not match {}'.format(sceneid))

    precollection_pattern = (
        r'^L'
        r'(?P<sensor>\w{1})'
        r'(?P<satellite>\w{1})'
        r'(?P<path>[0-9]{3})'
        r'(?P<row>[0-9]{3})'
        r'(?P<acquisitionYear>[0-9]{4})'
        r'(?P<acquisitionJulianDay>[0-9]{3})'
        r'(?P<groundStationIdentifier>\w{3})'
        r'(?P<archiveVersion>[0-9]{2})$'
    )

    collection_pattern = (
        r'^L'
        r'(?P<sensor>\w{1})'
        r'(?P<satellite>\w{2})'
        r'_'
        r'(?P<processingCorrectionLevel>\w{4})'
        r'_'
        r'(?P<path>[0-9]{3})'
        r'(?P<row>[0-9]{3})'
        r'_'
        r'(?P<acquisitionYear>[0-9]{4})'
        r'(?P<acquisitionMonth>[0-9]{2})'
        r'(?P<acquisitionDay>[0-9]{2})'
        r'_'
        r'(?P<processingYear>[0-9]{4})'
        r'(?P<processingMonth>[0-9]{2})'
        r'(?P<processingDay>[0-9]{2})'
        r'_'
        r'(?P<collectionNumber>\w{2})'
        r'_'
        r'(?P<collectionCategory>\w{2})$'
    )

    meta = None
    for pattern in [collection_pattern, precollection_pattern]:
        match = re.match(pattern, sceneid, re.IGNORECASE)
        if match:
            meta = match.groupdict()
            break

    if not meta:
        raise ValueError('Could not match {}'.format(sceneid))

    if meta.get('acquisitionJulianDay'):
        date = datetime.datetime(int(meta['acquisitionYear']), 1, 1) + datetime.timedelta(int(meta['acquisitionJulianDay']) - 1)
        meta['date'] = date.strftime('%Y-%m-%d')
    else:
        meta['date'] = '{}-{}-{}'.format(meta['acquisitionYear'], meta['acquisitionMonth'], meta['acquisitionDay'])

    collection = meta.get('collectionNumber', '')
    if collection != '':
        collection = 'c{}'.format(int(collection))

    meta['key'] = os.path.join(collection, 'L8', meta['path'], meta['row'], sceneid, sceneid)

    meta['scene'] = sceneid

    return meta

################################################################################
def linear_rescale(image, in_range=[0,16000], out_range=[1,255]):
    '''
    Linear rescaling
    '''

    imin, imax = in_range
    omin, omax = out_range
    image = np.clip(image, imin, imax) - imin
    image = image / float(imax - imin)

    return (image * (omax - omin) + omin)
