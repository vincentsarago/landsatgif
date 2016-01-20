# landsatgif
Create High Resolution GIF animation From Landsat 8 images

![](/img/3bd4ddee-bba3-11e5-82f7-0c4de9b59fbf.gif)

A simple python script to create GIF from Landsat 8 image.

Philosophy of the 'method' is to select a point (search for data) and then create an AOI (extract pixels)

I'm reading data directly on Amazon Server, so date range should be set after January 1st 2015. 

Depends
-------
- gdal
- shapely
- numpy
- urllib2
- skimage

To Do
-------

- [x] Create a command line version
- [x] Test if multiple Path-Row
- [ ] Create a pure python version
- [ ] Create pip distribution
- [ ] Optimize GIF Creation
- [ ] Optimize color matching
  
More
-------

- Create Gif from low resolution Landsat Quicklook [landsat8evolution](http://remotepixel.ca/webmapping/landsat8evolution.html)
- Search and Download Landsat data [landsat-util](https://github.com/developmentseed/landsat-util) from @developmentseed
- Create GIF for entire Landsat image (in bash) [landsat-gifworks](https://github.com/KAPPS-/landsat-gifworks) from @KAPPS-
