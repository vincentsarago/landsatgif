# -*- coding: utf-8 -*-

import os
import sys
import datetime
import urllib2
import numpy as np
import requests
import uuid
import json

from skimage import exposure
from osgeo import gdal, ogr, osr
from shapely.wkt import loads

##############################################################

tmp_dir = '/tmp/'
out_dir = '~/'

###########
# INPUT
pr = None
lat = 45.542167 #Montréal
lon = -73.626149 #Montréal
cc = 20
start_date = '2015-01-01'
end_date = '2016-01-01'

buff_size = 10000 #in m

##############
landsat_api_url = 'https://api.remotepixel.ca/landsat'
#or
#landsat_api_url = 'https://api.developmentseed.org/landsat'
##############

##########################   
#Form Landsat-util by developmentseed.org (https://github.com/developmentseed/landsat-util)
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
                              'sat_type': u'L8',
                              'path': '{:03d}'.format(int(i['path'])),
                              'row': '{:03d}'.format(int(i['row'])),
                              'browseURL': i['browseURL'],
                              'date': i['acquisitionDate'],
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

def worker(_taskid=None):
    """ Create animated GIF from landsat 8 data"""
    if not _taskid:
        _taskid = str(uuid.uuid1())

    #Query Scenes
    landsat_query = query_builder(paths_rows=pr, lat=lat, lon=lon, start_date=start_date, end_date=end_date, cloud_max=cc)

    candidate_scenes = search(landsat_query)
    im2process = candidate_scenes['results']

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
    polB = shPt.buffer(buff_size, cap_style=3)
    
    aoi = ogr.CreateGeometryFromWkt(polB.wkt)
    aoi.Transform(wmTowgs) #Transform AOI in WGS84
    pt = pol = polB = None

    #Check if multiple Path Row
    
    
    ######
    
    #Check if AOI is within Landsat Scene
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
        print 'no Image found'  
    else:
        
        #print proc_images
        workdir = os.path.join(tmp_dir, _taskid)
        if not os.path.exists(workdir):
            os.makedirs(workdir, 0775)

        l8_images = []
        date_array = []        
        for ii in range(len(proc_images)):
             
            im = proc_images[ii]
            out_im = os.path.join(workdir, '{}.tif'.format(im['date']))
            try:
                WRSPath = im['path']
                WRSRow = im['row']
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
          
                driver = gdal.GetDriverByName("GTiff")
                dst_ds = driver.Create(out_im, x_size, y_size, 3, gdal.GDT_Byte)
                dst_ds.SetGeoTransform(tuple(ngeo))
                dst_ds.SetProjection(proj)
                rgb = [4,3,2]
          
                for b in range(len(rgb)):
                    band_address = '/vsicurl/{0}_B{1}.TIF'.format(landsat_address, rgb[b])
                    awsim = gdal.Open(band_address, gdal.GA_ReadOnly)
                    #2% color rescale
                    arr = awsim.GetRasterBand(1).ReadAsArray(x_off, y_off, x_size, y_size) 
                    p2, p98 = np.percentile(arr[arr > 0], (2, 98))
                    dst_ds.GetRasterBand(b+1).WriteArray(np.where(arr > 0, exposure.rescale_intensity(arr, in_range=(p2, p98), out_range=(1,255)), 0))
                    dst_ds.GetRasterBand(b+1).SetNoDataValue(0)
                    awsim = None
                      
                dst_ds = None    # save, close
  
                #Convert TIF in JPG and add date
                str1 = 'convert -font Helvetica -pointsize 30 -fill white -draw "text 20,50 \''
                str2 = im['date'] + '\'"'
                out_jpg = out_im.replace('.tif','.jpg')
                cmd = "%s%s %s %s" % (str1, str2, out_im, out_jpg)
                os.system(cmd)
                os.remove(out_im) #delete TIF
                
                date_array.append(im['date'])
                l8_images.append(out_jpg)
            except:
                print 'failed'

        #Sort image by date
        sorted_index = np.argsort(date_array)
        l8sort = [l8_images[i] for i in sorted_index]
        for i in range(len(l8sort)):
            os.rename(l8sort[i], os.path.join(workdir, '{:05d}.jpg'.format(i)))
    
    #Create GIF
    gif_file = os.path.join(out_dir, "%s.gif" % _taskid)
    inJpg = os.path.join(workdir, "*.jpg")
    os.system('convert -delay 30 -depth 8 -layers optimize -quality 80 -loop 0 {0} {1}'.format(inJpg, gif_file))
    os.system('rm -rf {}'.format(workdir))

if __name__ == '__main__':
    worker()
