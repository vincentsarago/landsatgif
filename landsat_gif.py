# -*- coding: utf-8 -*-

import click

import os
import sys
import re
import urllib2
import numpy as np
import requests
import shutil
import uuid
import json
import math
import time
from PIL import Image, ImageFont, ImageDraw
from skimage import exposure
from osgeo import gdal, ogr, osr
from shapely.wkt import loads

##########################   
#From Landsat-util by developmentseed.org (https://github.com/developmentseed/landsat-util)
def query_builder(paths_rows=None, lat=None, lon=None, start_date=None, end_date=None,
                  cloud_min=None, cloud_max=None):
    """ Builds the proper search syntax (query) for Landsat API """

    query = []
    or_string = ''
    and_string = ''
    search_string = ''

    if paths_rows:
        # Coverting rows and paths to paired list
        new_array = create_paired_list(paths_rows)
        paths_rows = ['(%s)' % row_path_builder(i[0], i[1]) for i in new_array]
        or_string = '+OR+'.join(map(str, paths_rows))

    if start_date and end_date:
        query.append(date_range_builder(start_date, end_date))
    elif start_date:
        query.append(date_range_builder(start_date, '2100-01-01'))
    elif end_date:
        query.append(date_range_builder('2009-01-01', end_date))

    if cloud_min and cloud_max:
        query.append(cloud_cover_prct_range_builder(cloud_min, cloud_max))
    elif cloud_min:
        query.append(cloud_cover_prct_range_builder(cloud_min, '100'))
    elif cloud_max:
        query.append(cloud_cover_prct_range_builder('-1', cloud_max))

    if lat and lon:
        query.append(lat_lon_builder(lat, lon))

    if query:
        and_string = '+AND+'.join(map(str, query))

    if and_string and or_string:
        search_string = and_string + '+AND+(' + or_string + ')'
    else:
        search_string = or_string + and_string

    return search_string

def row_path_builder(path='', row=''):
    """
    Builds row and path query
    Accepts row and path in XXX format, e.g. 003
    """
    return 'path:%s+AND+row:%s' % (path, row)

def date_range_builder(start='2013-02-11', end=None):
    """
    Builds date range query
    Accepts start and end date in this format YYYY-MM-DD
    """
    if not end:
        end = time.strftime('%Y-%m-%d')

    return 'acquisitionDate:[%s+TO+%s]' % (start, end)

def cloud_cover_prct_range_builder(min=0, max=100):
    """
    Builds cloud cover percentage range query
    Accepts bottom and top range in float, e.g. 1.00
    """
    return 'cloudCoverFull:[%s+TO+%s]' % (min, max)

def lat_lon_builder(lat=0, lon=0):
    """ Builds lat and lon query """
    return ('upperLeftCornerLatitude:[%s+TO+1000]+AND+lowerRightCornerLatitude:[-1000+TO+%s]'
            '+AND+lowerLeftCornerLongitude:[-1000+TO+%s]+AND+upperRightCornerLongitude:[%s+TO+1000]'
            % (lat, lat, lon, lon))

def create_paired_list(value):
    """ Create a list of paired items from a string.
    :param value:
        the format must be 003,003,004,004 (commas with no space)
    :type value:
        String
    :returns:
        List
    :example:
        >>> create_paired_list('003,003,004,004')
        [['003','003'], ['004', '004']]
    """

    if isinstance(value, list):
        value = ",".join(value)

    array = re.split('\D+', value)

    # Make sure the elements in the list are even and pairable
    if len(array) % 2 == 0:
        new_array = [list(array[i:i + 2]) for i in range(0, len(array), 2)]
        return new_array
    else:
        raise ValueError('The string should include pairs and be formated. '
                         'The format must be 003,003,004,004 (commas with '
                         'no space)')

def search(quer, limit=200):
    """ Call landsat api and return landsat scenes"""
    r = requests.get('%s?search=%s&limit=%s' % (landsat_api_url, quer, limit))

    r_dict = json.loads(r.text)
    result = {}

    if 'error' in r_dict:
        result['status'] = u'error'
        result['code'] = r_dict['error']['code']
        result['message'] = r_dict['error']['message']

    elif 'meta' in r_dict:
        result['status'] = u'SUCCESS'
        result['total'] = r_dict['meta']['results']['total']
        result['results'] = [{'sceneID': i['sceneID'],
                              'path': '{:03d}'.format(int(i['path'])),
                              'row': '{:03d}'.format(int(i['row'])),
                              'date': i['acquisitionDate'],
                              'dayOrNight': i['dayOrNight'], 
                              'lowerLeftCornerLatitude':i['lowerLeftCornerLatitude'],
                              'lowerLeftCornerLongitude':i['lowerLeftCornerLongitude'],
                              'lowerRightCornerLatitude':i['lowerRightCornerLatitude'],
                              'lowerRightCornerLongitude':i['lowerRightCornerLongitude'],
                              'upperLeftCornerLatitude':i['upperLeftCornerLatitude'],
                              'upperLeftCornerLongitude':i['upperLeftCornerLongitude'],
                              'upperRightCornerLatitude':i['upperRightCornerLatitude'],
                              'upperRightCornerLongitude':i['upperRightCornerLongitude'],
                              'cloud': i['cloudCoverFull']}
                             for i in r_dict['results']]

    return result
##########################   

##############################################################
# landsat_extractMTL()
# Extract Metadata value
#
def landsat_extractMTL(meta, param):
    """ Extract Parameters from MTL file """
    
    for line in meta:
        data = line.split(' = ')
        if (data[0]).strip() == param:
            return (data[1]).strip()
        
##############################################################
#Conversion Top Of Atmosphere planetary reflectance
#REF: http://landsat.usgs.gov/Landsat8_Using_Product.php
def landsat_dnToReflectance_USGS(dn, nband, mfile):
    """ Apply correction - DN to TOA value """
    
    Mp = float(landsat_extractMTL(mfile, "REFLECTANCE_MULT_BAND_%i" % nband))
    Ap = float(landsat_extractMTL(mfile, "REFLECTANCE_ADD_BAND_%i" % nband))
    SE = math.radians(float(landsat_extractMTL(mfile, "SUN_ELEVATION")))
    Reflect_toa = (np.where(dn > 0, (Mp*dn + Ap) / math.sin(SE), 0))
    return Reflect_toa

################################################################################
################################################################################
################################################################################

##############
landsat_api_url = 'https://api.remotepixel.ca/landsat'
#or
#landsat_api_url = 'https://api.developmentseed.org/landsat'
##############

@click.group()
def cli():
    pass

@cli.command()
@click.option('--lat', type=float, default=None,
    help='Latitude of the query, between 90 and -90.')
@click.option('--lon', type=float, default=None,
    help='Longitude of the query, between 180 and -180.')
@click.option(
    '--path_row', type=str, default=None,
    help='Paths and Rows in order separated by comma. Use quotes "001,003".')

@click.option(
    '--cloud', type=float, default=20.,
    help='Start date of the query in the format YYYYMMDD.')
@click.option(
    '--start_date', type=str, default='2015-01-01',
    help='Start date of the query in the format YYYY-MM-DD.')
@click.option(
    '--end_date', type=str, default=time.strftime('%Y-%m-%d'),
    help='End date of the query in the format YYYY-MM-DD.')
@click.option(
    '--buffer', type=int, default=10000,
    help='Buffer size around lat/lon point for image creation.')
@click.option(
    '--taskid', type=str, default=str(uuid.uuid1()),
    help='UUID of task.')
@click.option(
    '--ndvi', is_flag=True,
    help='Create NDVI animation instead of RGB')
@click.option(
    '--aws', is_flag=True,
    help='If you are running this code on AWS.')
@click.option(
    '--path', type=click.Path(exists=True), default='.',
    help='Set the path where the file will be saved.')

def worker(lat, lon, cloud, path_row, start_date, end_date, buffer, taskid, ndvi, path, aws):
    """ Create animated GIF from landsat 8 data"""

    #Test 
    #lat lon has to be defined if path_row isn't 
    if (not lat) | (not lon):
        print "No defined lat-lon"
        if (not path_row):
            print "No defined Path-Row for query as well"
            print "Cannot perform querry, please make sure to include at least lat and lon options"
            sys.exit(1)

    #Query Scenes
    print
    print "Building Landsat-API request"
    landsat_query = query_builder(paths_rows=path_row, lat=lat, lon=lon, start_date=start_date, end_date=end_date, cloud_max=cloud)
    print "Searching Landsat 8 images"
    candidate_scenes = search(landsat_query)


    if not candidate_scenes.has_key('results'):
        print "Landsat-API Querry returned with 'Not Found message'"
        sys.exit(1)
        
    im2process = candidate_scenes['results']
    all_ids = [i['sceneID'] for i in im2process]
    
    print '{} Landsat scene found'.format(len(all_ids))
    print 'landsat ids: {}'.format(", ".join(all_ids))

    #Check Only if ROW is the same (same date) 
    all_pr = ['{:03d},{:03d}'.format(int(i['path']),int(i['row'])) for i in im2process]
    all_row = [i['row'] for i in im2process]
    if len(list(set(all_row))) > 1:
        print '''AOI covering more than one Row : 
        Please choose one of the following: {}
        Using --pathrow option'''.format(' | '.join(list(set(all_pr))))
        sys.exit(1)
    
    #Construct AOI  (square in WebMercator)
    wgs = osr.SpatialReference()  
    wgs.ImportFromEPSG(4326)
     
    wmerc = osr.SpatialReference()  
    wmerc.ImportFromEPSG(3857)
    wgsTowm = osr.CoordinateTransformation(wgs, wmerc)    
    wmTowgs = osr.CoordinateTransformation(wmerc, wgs)    
    
    #Create AOI - 10km buffer square (WebMercator) around point 
    pt = ogr.Geometry(ogr.wkbPoint)
    pt.AddPoint(lon, lat)
    
    pt.Transform(wgsTowm)
    shPt = loads(pt.ExportToWkt())
    polB = shPt.buffer(buffer, cap_style=3)
    
    aoi = ogr.CreateGeometryFromWkt(polB.wkt)
    aoi.Transform(wmTowgs) #Transform AOI in WGS84
    pt = pol = polB = None
    
    print "Excluding Landsat 8 scene not covering the AOI"
    proc_images = []
    for ii in range(len(im2process)):
        imgMeta = im2process[ii]

        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(imgMeta['lowerLeftCornerLongitude'], imgMeta['lowerLeftCornerLatitude'])
        ring.AddPoint(imgMeta['upperLeftCornerLongitude'], imgMeta['upperLeftCornerLatitude'])
        ring.AddPoint(imgMeta['upperRightCornerLongitude'], imgMeta['upperRightCornerLatitude'])
        ring.AddPoint(imgMeta['lowerRightCornerLongitude'], imgMeta['lowerRightCornerLatitude'])
        ring.AddPoint(imgMeta['lowerLeftCornerLongitude'], imgMeta['lowerLeftCornerLatitude'])
        poly = ogr.Geometry(ogr.wkbPolygon)
        poly.AddGeometry(ring)

        if aoi.Within(poly):
            proc_images.append(imgMeta)
        
        ring = poly = None
     
    if len(proc_images) == 0:
        print 'No Image found covering the AOI - try reducing buffer size or changing lat-lon'  
    else:
        workdir = os.path.join(path, taskid)
        if not os.path.exists(workdir):
            os.makedirs(workdir, 0775)

        font = ImageFont.load_default().font
        
        l8_images = []
        date_array = []        
        for ii in range(len(proc_images)):
             
            im = proc_images[ii]
            print 'Processing Landsat image {}'.format(im['sceneID'])
            
            out_im = os.path.join(workdir, '{}.tif'.format(im['date']))
            
            try:
                WRSPath = im['path']
                WRSRow = im['row']
                if aws:
                    landsat_address = 's3://landsat-pds/L8/{path}/{row}/{id}/{id}'.format(path=WRSPath, row=WRSRow, id=im['sceneID'])
                else: 
                    landsat_address = 'http://landsat-pds.s3.amazonaws.com/L8/{path}/{row}/{id}/{id}'.format(path=WRSPath, row=WRSRow, id=im['sceneID'])
                                       
                meta_file = '{0}_MTL.txt'.format(landsat_address)
                meta_data = urllib2.urlopen(meta_file).readlines()
                
                #Get Landsat scene geographic metadata
                bqa = '/vsicurl/{addr_name}_BQA.TIF'.format(addr_name=landsat_address)
                src_ds = gdal.Open(bqa, gdal.GA_ReadOnly)
                geoT = src_ds.GetGeoTransform()
                proj = src_ds.GetProjection()
                src_ds = None
          
                imSpatialRef = osr.SpatialReference()
                imSpatialRef.ImportFromWkt(proj)
          
                aoiSpatialRef = osr.SpatialReference()
                aoiSpatialRef.ImportFromEPSG(4326)
                coordTransform = osr.CoordinateTransformation(aoiSpatialRef, imSpatialRef)
      
                aoi.Transform(coordTransform) # reproject the aoi in UTM
                aoi_bounds = aoi.GetEnvelope()
          
                x_off = int((aoi_bounds[0] - geoT[0]) / geoT[1])
                y_off = int((aoi_bounds[3] - geoT[3]) / geoT[5])             
                x_size = int(((aoi_bounds[0] - geoT[3]) / geoT[5]) - ((aoi_bounds[1] - geoT[3]) / geoT[5]))
                y_size = int(((aoi_bounds[2] - geoT[3]) / geoT[5]) - ((aoi_bounds[3] - geoT[3]) / geoT[5]))
    
                #Create RGB file
                ngeo = list(geoT)
                ngeo[0] = aoi_bounds[0]
                ngeo[3] = aoi_bounds[3]
            
                if ndvi:
                    driver = gdal.GetDriverByName("GTiff")
                    dst_ds = driver.Create(out_im, x_size, y_size, 1, gdal.GDT_Byte)
                    dst_ds.SetGeoTransform(tuple(ngeo))
                    dst_ds.SetProjection(proj)
    
                    band5_address = '/vsicurl/{0}_B5.TIF'.format(landsat_address)
                    awsim5 = gdal.Open(band5_address, gdal.GA_ReadOnly)
                    arr5 = awsim5.GetRasterBand(1).ReadAsArray(x_off, y_off, x_size, y_size) 
                    arr5 = landsat_dnToReflectance_USGS(arr5, 5, meta_data) 
                    
                    band4_address = '/vsicurl/{0}_B4.TIF'.format(landsat_address)
                    awsim4 = gdal.Open(band4_address, gdal.GA_ReadOnly)
                    arr4 = awsim4.GetRasterBand(1).ReadAsArray(x_off, y_off, x_size, y_size) 
                    arr4 = landsat_dnToReflectance_USGS(arr4, 4, meta_data)    

                    ratio = np.where( arr5*arr4 > 0, np.nan_to_num((arr5 - arr4) / (arr5 + arr4)), 0)
                    dst_ds.GetRasterBand(1).WriteArray(exposure.rescale_intensity(ratio, in_range=(-1,1), out_range=(1,255)))
                    #dst_ds.GetRasterBand(1).SetNoDataValue(0)
                    ratio = dst_ds = awsim4 = awsim5 = arr4 = arr5 = None
                    
                    #Add color palette!
                                        
                    img = Image.open(out_im).convert('RGB')
                    draw = ImageDraw.Draw(img)
                    xs,ys = draw.textsize(im['date'],  font=font)
                    draw.rectangle([ (5, 5), (xs+15, ys+15) ], fill=(255,255,255))
                    draw.text((10, 10), im['date'], (0,0,0), font=font)
                    out_jpg = out_im.replace('.tif','.jpg')
                    img.save(out_jpg)                
                    os.remove(out_im)                

                else:
                    driver = gdal.GetDriverByName("GTiff")
                    dst_ds = driver.Create(out_im, x_size, y_size, 3, gdal.GDT_Byte)
                    dst_ds.SetGeoTransform(tuple(ngeo))
                    dst_ds.SetProjection(proj)
                    rgb = [4,3,2]
                    for b in range(len(rgb)):
                        band_address = '/vsicurl/{0}_B{1}.TIF'.format(landsat_address, rgb[b])
                        awsim = gdal.Open(band_address, gdal.GA_ReadOnly)
                        arr = awsim.GetRasterBand(1).ReadAsArray(x_off, y_off, x_size, y_size)                                       
                        p2, p98 = np.percentile(arr[arr > 0], (2, 98))
                        dst_ds.GetRasterBand(b+1).WriteArray(np.where(arr > 0, exposure.rescale_intensity(arr, in_range=(p2, p98), out_range=(1,255)), 0))
                        dst_ds.GetRasterBand(b+1).SetNoDataValue(0)
                        awsim = arr = None
                    dst_ds = None    # save, close
              
                    img = Image.open(out_im)
                    draw = ImageDraw.Draw(img)
                    xs,ys = draw.textsize(im['date'],  font=font)
                    draw.rectangle([ (5, 5), (xs+15, ys+15) ], fill=(255,255,255))
                    draw.text((10, 10), im['date'], (0,0,0), font=font)
                    out_jpg = out_im.replace('.tif','.jpg')
                    img.save(out_jpg)                
                    os.remove(out_im)
                    
                date_array.append(im['date'])
                l8_images.append(out_jpg)
            except:
                print 'Failed to process Landsat image {}'.format(im['sceneID'])

        if len(date_array) > 0:
            #Sort image by date and rename with number
            sorted_index = np.argsort(date_array)
            l8sort = [l8_images[i] for i in sorted_index]
            for i in range(len(l8sort)):
                os.rename(l8sort[i], os.path.join(workdir, '{:05d}.jpg'.format(i)))
        
            #This part can be replace in pure python
            #Create GIF
            gif_file = os.path.join(path, "%s.gif" % taskid)
            inJpg = os.path.join(workdir, "*.jpg")
            os.system('convert -delay 30 -depth 8 -layers optimize -quality 80 -loop 0 {0} {1}'.format(inJpg, gif_file))
        
        shutil.rmtree(workdir)

if __name__ == '__main__':
    worker()
