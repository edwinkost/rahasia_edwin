#-iterates over the major basins and optimizes the fraction recharge set aside
# for environmental flow conditions
import os, zlib,zipfile
from scipy import optimize
import numpy as np
import PCRaster as pcr
from PCRaster.NumPy import pcr2numpy, numpy2pcr
from PCRaster.Framework import generateNameT

monthlyArchiveFile= 'cru_alpha_sc_results.zip'
specificQArchiveFile= 'cru_specificrunoff_results.zip'
rootQSpecFileNames= ['waterrunoff%s.map','landrunoff%s.map']
rootQFileName= 'qc'
MV= -999.
startYear= 1958; endYear= 2001
yearList= range(startYear,endYear+1)
rootR3AVGFileName= 'r3_avg%s.map'
LDD= pcr.readmap('glwd_lddlake.map')
LDDBasins= pcr.readmap('glwd130m_ldd.map')
cellArea= pcr.readmap('cellarea30.map')
fracWat= pcr.readmap('glwd130m_fracw.map')
lakeMask= pcr.readmap('lake.map') != 0
catchments= pcr.catchment(LDDBasins,pcr.pit(LDDBasins))
pcr.report(catchments,'catchments.map')
maximumCatchmentID= pcr.cellvalue(pcr.mapmaximum(pcr.scalar(catchments)),1)[0]
catchmentSizeLimit= 0.

#-main
#-opening zip file
print 'extracting information from zip file'
currentPath= os.getcwd()
zipArchive= zipfile.ZipFile(monthlyArchiveFile)

print 'processing maps: discharge over %d-%d' % (startYear,endYear)
iCnt= 0
yearStartPos= len(rootQFileName)
yearEndPos= yearStartPos+4
#-loop through zip file and retrieve relevant maps
for fileName in zipArchive.namelist():
  if rootQFileName in fileName and not 'ini' in fileName:
    try:
      year= int(fileName[yearStartPos:yearEndPos])
      month= int(fileName.split('.')[1])
    except:
      year= 0
    if year in yearList:
      monthCnt= (year-startYear)*12+month
      tempFile= open(fileName,'wb')
      tempFile.write(zipArchive.read(fileName))
      tempFile.close()
      mapArray= pcr2numpy(pcr.readmap(fileName),MV)
      os.remove(fileName)
      mask= mapArray != MV
      if iCnt != 0:
        #-array exists, stack vertically
        mapStack= np.vstack((mapStack,mapArray[mask]))
        monthStack= np.vstack((monthStack,[monthCnt]))
      else:
        #-array has to be created
        mapStack= mapArray[mask]
        monthStack= np.array([monthCnt])
        coordinates= np.zeros((mapStack.size,2))
        pcr.setglobaloption('unitcell')
        mapArray= pcr2numpy(pcr.ycoordinate(pcr.boolean(1))+0.5,MV)
        coordinates[:,0]= mapArray[mask]
        mapArray= pcr2numpy(pcr.xcoordinate(pcr.boolean(1))+0.5,MV)
        coordinates[:,1]= mapArray[mask]      
      iCnt+= 1
      print '%d' % iCnt,

print
#-map stack created and sorted here, keeping indices
# values are sorted over 2nd dimension of array, representing the points on the (ravelled) map
print 'sorting values'
indices= np.zeros((mapStack.shape),np.uint)
monthStack= np.zeros((mapStack.shape))+monthStack
for iCnt in xrange(mapStack.shape[1]):
  indices[:,iCnt]= mapStack[:,iCnt].argsort(kind= 'mergesort')
  mapStack[:,iCnt]= mapStack[:,iCnt][indices[:,iCnt]]
  monthStack[:,iCnt]= monthStack[:,iCnt][indices[:,iCnt]]
#-extract values for percentiles
print 'returning maps'
for percent in range(10,110,10):
  percentile= 0.01*percent
  print percent,
  index0= min(mapStack.shape[0]-1,int(percentile*mapStack.shape[0]))
  index1= min(mapStack.shape[0]-1,int(percentile*mapStack.shape[0])+1)
  x0= float(index0)/mapStack.shape[0]
  x1= float(index1)/mapStack.shape[0]
  if x0 <> x1:
    y= mapStack[index0,:]+(percentile-x0)*\
       (mapStack[index1,:]-mapStack[index0,:])/(x1-x0)
  else:
    y= mapStack[index0,:]
  #-convert a slice of the stack into an array
  mapArray= np.ones((mapArray.shape))*MV
  for iCnt in xrange(coordinates.shape[0]):
    row= coordinates[iCnt,0]-1
    col= coordinates[iCnt,1]-1
    mapArray[row,col]= y[iCnt]
  pcr.report(numpy2pcr(pcr.Scalar,mapArray,MV),'q%03d_cumsec.map' % percent)
print
#-retrieve average recharge
R3AVG= pcr.scalar(0.)
for year in yearList:
  fileName= rootR3AVGFileName % ('%04d' % year)
  tempFile= open(fileName,'wb')
  tempFile.write(zipArchive.read(fileName))
  tempFile.close()  
  R3AVG+= pcr.readmap(fileName)
  os.remove(fileName)
R3AVG/= len(yearList)
pcr.report(R3AVG,rootR3AVGFileName % '')
print 'retrieving average runoff components'
for rootQSpecFileName in rootQSpecFileNames:
  specificRunoffQ= pcr.scalar(0.)
  for year in yearList:
    fileName= rootQSpecFileName % ('%04d' % year)
    tempFile= open(fileName,'wb')
    tempFile.write(zipArchive.read(fileName))
    tempFile.close()  
    specificRunoffQ+= pcr.readmap(fileName)
    os.remove(fileName)
  specificRunoffQ/= len(yearList)
  pcr.report(specificRunoffQ,rootQSpecFileName % 'avg')
#-closing zip file
zipArchive.close()
#-re-read created maps (mainly for environmental Q which is not defined in advance)
environmentalQ= pcr.readmap('q010_cumsec.map')
R3AVG= pcr.readmap(rootR3AVGFileName % '')
waterSpecificRunoff= pcr.readmap(rootQSpecFileNames[0] % 'avg')
landSpecificRunoff= pcr.readmap(rootQSpecFileNames[1] % 'avg')
#-open text file for output
textFile= open('catchment_groundwatercontribution.txt','w')
repStr= 'Environmental flow analysis per basin, resulting in a map of renewable, exploitable recharge\n'
textFile.write(repStr)
print repStr
#-report global totals
repStr= 'global contributions to runoff [km3]:\n'+\
  'water: %.1f\n' % (1.e-9*pcr.cellvalue(pcr.maptotal(waterSpecificRunoff*fracWat*cellArea),1)[0]) +\
  'land: %.1f\n' % (1.e-9*pcr.cellvalue(pcr.maptotal(landSpecificRunoff*(1.-fracWat)*cellArea),1)[0]) +\
  'groundwater: %.1f\n' % (1.e-9*pcr.cellvalue(pcr.maptotal(R3AVG*365.25*(1.-fracWat)*cellArea),1)[0])
textFile.write(repStr)
print repStr
#-optimize recharge reserved for ecological flow for catchments that are not mere lakes
repStr= 'processing %d catchments; all flows expressed as volumes in m3 at the outlet of the catchment\n' % maximumCatchmentID
print repStr
textFile.write(repStr)
#-initialize map of reserved recharge fraction
fractionReservedRechargeMap= pcr.scalar(0.)
#-create header to display on screen and write to file
repStr= '%6s,%15s,%15s,%15s,%15s,%15s,%15s,%15s,%15s,%15s\n' % \
  ('ID','Area [km2]','Q_Avg [m3]','Q_10 [m3]','Q_10/Q_Avg [-]','q_water [m3]','q_land [m3]','R_gw (pos.)','R_gw/q_land [-]','R_Q10/R_gw [-]')
print repStr
textFile.write(repStr)
for catchment in xrange(1,maximumCatchmentID+1):
  #-create catchment mask and check whether it does not coincide with a lake
  catchmentMask= catchments == catchment
  catchmentSize= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,cellArea*1.e-6)),1)[0]
  if pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,pcr.scalar(lakeMask))),1) <> \
      pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,pcr.scalar(catchmentMask))),1)[0] and \
      catchmentSize > catchmentSizeLimit:
    #-valid catchment, process
    catchmentRecharge= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,pcr.max(0.,R3AVG)*365.25*(1.-fracWat)*cellArea)),1)[0]
    catchmentLandRunoff= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,landSpecificRunoff*(1.-fracWat)*cellArea)),1)[0]
    catchmentWaterRunoff= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,waterSpecificRunoff*fracWat*cellArea)),1)[0]
    catchmentRunoff= pcr.cellvalue(pcr.mapmaximum(pcr.ifthen(catchmentMask,\
      pcr.accuthresholdflux(LDD,(fracWat*pcr.max(0.,waterSpecificRunoff)+\
      (1.-fracWat)*landSpecificRunoff)*cellArea,fracWat*pcr.max(0.,-waterSpecificRunoff)*cellArea))),1)[0]
    catchmentEnvironmentalFlow= pcr.cellvalue(pcr.mapmaximum(pcr.ifthen(catchmentMask,environmentalQ)),1)[0]*365.25*3600*24
    catchmentRunoff= max(catchmentRunoff,catchmentEnvironmentalFlow)
    #-groundwater recharge required to satisfy environmental flow conditions depends on the fraction environmental flow over the mean discharge
    # and the fraction contribution of the land runoff to the mean discharge
    if catchmentLandRunoff > 0:
      fractionGroundwaterContribution= min(1.,catchmentRecharge/catchmentLandRunoff)
    else:
      fractionGroundwaterContribution= 1.
    if catchmentRunoff > 0.:
      fractionEnvironmentalFlow= catchmentEnvironmentalFlow/catchmentRunoff
      fractionLandRunoffContribution= catchmentLandRunoff/catchmentRunoff
    else:
      fractionEnvironmentalFlow= 1.
      fractionLandRunoffContribution= 1.
    fractionReservedRecharge= min(1.,fractionEnvironmentalFlow*fractionLandRunoffContribution)
    #-echo to screen, and write to file and map
    repStr= '%6d,%15.1f,%15.6g,%15.6g,%15.6f,%15.6g,%15.6g,%15.6g,%15.6f,%15.6f\n' % \
      (catchment,catchmentSize,catchmentRunoff,catchmentEnvironmentalFlow,\
       fractionEnvironmentalFlow,catchmentWaterRunoff,catchmentLandRunoff,catchmentRecharge,\
       fractionGroundwaterContribution,fractionReservedRecharge)
    print repStr
    textFile.write(repStr)
    #-update map
    fractionReservedRechargeMap= pcr.ifthenelse(catchmentMask,\
      pcr.scalar(fractionReservedRecharge),fractionReservedRechargeMap)   
#-report map and close text file
pcr.report(fractionReservedRechargeMap,'fraction_reservedrecharge.map')
textFile.close()
print 'all done!'
