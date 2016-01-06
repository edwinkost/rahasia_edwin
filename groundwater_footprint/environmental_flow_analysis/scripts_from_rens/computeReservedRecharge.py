#-import modules
import os, sys, datetime, calendar
import numpy as np
import pcraster as pcr
from pcraster import pcr2numpy, numpy2pcr
import pcraster.framework as pcrm
from pcraster.framework import generateNameT

#-add folders with specific modules to the python path
sys.path.insert(0,'/home/beek0120/PCRGLOBWB/scripts/pcrTools')

#-import additional modules
from pcrParameterization import pcrObject
from spatialDataSet2PCR import spatialAttributes

def main():
	#-initialization
	# MVs
	MV= -999.
	# minimum catchment size to process
	catchmentSizeLimit= 0.0
	# period of interest, start and end year
	startYear= 1961
	endYear= 2010
	# maps
	cloneMapFileName= '/data/hydroworld/PCRGLOBWB20/input30min/global/Global_CloneMap_30min.map'
	lddFileName= '/data/hydroworld/PCRGLOBWB20/input30min/routing/lddsound_30min.map'
	cellAreaFileName= '/data/hydroworld/PCRGLOBWB20/input30min/routing/cellarea30min.map'
	# set clone 
	pcr.setclone(cloneMapFileName)
	# output
	outputPath= '/scratch/rens/reservedrecharge'
	percentileMapFileName= os.path.join(outputPath,'q%03d_cumsec.map')
	textFileName= os.path.join(outputPath,'groundwater_environmentalflow_%d.txt')
	fractionReservedRechargeMapFileName= os.path.join(outputPath,'fraction_reserved_recharge%d.map')
	fractionMinimumReservedRechargeMapFileName= os.path.join(outputPath,'minimum_fraction_reserved_recharge%d.map')
	# input
	inputPath= '/nfsarchive/edwin-emergency-backup-DO-NOT-DELETE/rapid/edwin/05min_runs_results/2015_04_27/non_natural_2015_04_27/global/netcdf/'
	# define data to be read from netCDF files
	ncData= {}
	variableName= 'totalRunoff'
	ncData[variableName]= {}
	ncData[variableName]['fileName']= os.path.join(inputPath,'totalRunoff_monthTot_output.nc')
	ncData[variableName]['fileRoot']= os.path.join(outputPath,'qloc')
	ncData[variableName]['annualAverage']= pcr.scalar(0)	
	variableName= 'gwRecharge'
	ncData[variableName]= {}
	ncData[variableName]['fileName']= os.path.join(inputPath,'gwRecharge_monthTot_output.nc')
	ncData[variableName]['fileRoot']= os.path.join(outputPath,'gwrec')
	ncData[variableName]['annualAverage']= pcr.scalar(0)
	variableName= 'discharge'
	ncData[variableName]= {}
	ncData[variableName]['fileName']= os.path.join(inputPath,'totalRunoff_monthTot_output.nc')
	ncData[variableName]['fileRoot']= os.path.join(outputPath,'qc')
	ncData[variableName]['annualAverage']= pcr.scalar(0)
	ncData[variableName]['mapStack']= np.array([])
	# percents and environmental flow condition set as percentile
	percents= range(10,110,10)
	environmentalFlowPercent= 10
	if environmentalFlowPercent not in percents:
		percents.append(environmentalFlowPercent)
		percents.sort()

	#-start
	# obtain attributes
	pcr.setclone(cloneMapFileName)
	cloneSpatialAttributes= spatialAttributes(cloneMapFileName)
	years= range(startYear,endYear+1)
	# output path
	if not os.path.isdir(outputPath):
		os.makedirs(outputPath)
	os.chdir(outputPath)
	# compute catchments
	ldd= pcr.readmap(lddFileName)
	cellArea= pcr.readmap(cellAreaFileName)
	catchments= pcr.catchment(ldd,pcr.pit(ldd))
	fractionWater= pcr.scalar(0.0) # temporary!
	lakeMask= pcr.boolean(0) # temporary!
	pcr.report(catchments,os.path.join(outputPath,'catchments.map'))
	maximumCatchmentID= int(pcr.cellvalue(pcr.mapmaximum(pcr.scalar(catchments)),1)[0])
	# iterate over years
	weight= float(len(years))**-1
	for year in years:
		#-echo year
		print ' - processing year %d' % year
		#-process data
		startDate= datetime.datetime(year,1,1)
		endDate= datetime.datetime(year,12,31)
		timeSteps= endDate.toordinal()-startDate.toordinal()+1
		dynamicIncrement= 1
		for variableName in ncData.keys():
			print '   extracting %s' % variableName,
			ncFileIn= ncData[variableName]['fileName']
			#-process data
			pcrDataSet= pcrObject(variableName, ncData[variableName]['fileRoot'],\
				ncFileIn,cloneSpatialAttributes, pcrVALUESCALE= pcr.Scalar, resamplingAllowed= True,\
				dynamic= True, dynamicStart= startDate, dynamicEnd= endDate, dynamicIncrement= dynamicIncrement, ncDynamicDimension= 'time')
			pcrDataSet.initializeFileInfo()
			pcrDataSet.processFileInfo()
			for fileInfo in pcrDataSet.fileProcessInfo.values()[0]:
				tempFileName= fileInfo[1]
				variableField= pcr.readmap(tempFileName)
				variableField= pcr.ifthen(pcr.defined(ldd),pcr.cover(variableField,0))
				if variableName == 'discharge':
					dayNumber= int(os.path.splitext(tempFileName)[1].strip('.'))
					date= datetime.date(year,1,1)+datetime.timedelta(dayNumber-1)
					numberDays= calendar.monthrange(year,date.month)[1]
					variableField= pcr.max(0,pcr.catchmenttotal(variableField*cellArea,ldd)/(numberDays*24*3600))
				ncData[variableName]['annualAverage']+= weight*variableField
				if 'mapStack' in ncData[variableName].keys():
					tempArray= pcr2numpy(variableField,MV)
					mask= tempArray != MV
					if ncData[variableName]['mapStack'].size != 0:
						ncData[variableName]['mapStack']= np.vstack((ncData[variableName]['mapStack'],tempArray[mask]))
					else:
						ncData[variableName]['mapStack']= tempArray[mask]
						coordinates= np.zeros((ncData[variableName]['mapStack'].size,2))
						pcr.setglobaloption('unitcell')
						tempArray= pcr2numpy(pcr.ycoordinate(pcr.boolean(1))+0.5,MV)
						coordinates[:,0]= tempArray[mask]
						tempArray= pcr2numpy(pcr.xcoordinate(pcr.boolean(1))+0.5,MV)
						coordinates[:,1]= tempArray[mask]      
				os.remove(tempFileName)				
			# delete object
			pcrDataSet= None
			del pcrDataSet
			# close line on screen
			print
	# report annual averages
	key= 'annualAverage'
	ncData['discharge'][key]/= 12
	for variableName in ncData.keys():
		ncData[variableName][key]= pcr.max(0,ncData[variableName][key])
		pcr.report(ncData[variableName][key],\
			os.path.join(outputPath,'%s_%s.map' % (variableName,key)))
	# remove aux.xml
	for tempFileName in os.listdir(outputPath):
		if 'aux.xml' in tempFileName:
			os.remove(tempFileName)
	# sort data
	print 'sorting discharge data'
	variableName= 'discharge'
	key= 'mapStack'
	indices= np.zeros((ncData[variableName][key].shape),np.uint)
	for iCnt in xrange(ncData[variableName][key].shape[1]):
		indices[:,iCnt]= ncData[variableName][key][:,iCnt].argsort(kind= 'mergesort')
		ncData[variableName][key][:,iCnt]= ncData[variableName][key][:,iCnt][indices[:,iCnt]]
	# extract values for percentiles
	print 'returning maps'
	for percent in percents:
		percentile= 0.01*percent
		index0= min(ncData[variableName][key].shape[0]-1,int(percentile*ncData[variableName][key].shape[0]))
		index1= min(ncData[variableName][key].shape[0]-1,int(percentile*ncData[variableName][key].shape[0])+1)
		x0= float(index0)/ncData[variableName][key].shape[0]
		x1= float(index1)/ncData[variableName][key].shape[0]
		if x0 <> x1:
			y= ncData[variableName][key][index0,:]+(percentile-x0)*\
				 (ncData[variableName][key][index1,:]-ncData[variableName][key][index0,:])/(x1-x0)
		else:
			y= ncData[variableName][key][index0,:]
		# convert a slice of the stack into an array
		tempArray= np.ones((cloneSpatialAttributes.numberRows,cloneSpatialAttributes.numberCols))*MV
		for iCnt in xrange(coordinates.shape[0]):
			row= coordinates[iCnt,0]-1
			col= coordinates[iCnt,1]-1
			tempArray[row,col]= y[iCnt]
		variableField= numpy2pcr(pcr.Scalar,tempArray,MV)
		pcr.report(variableField,percentileMapFileName % percent)
		if percent == environmentalFlowPercent:
			ncData[variableName]['environmentalFlow']= variableField
		tempArray= None; variableField= None
		del tempArray, variableField
	# process environmental flow
	# initialize map of reserved recharge fraction
	fractionReservedRechargeMap= pcr.ifthen(ncData[variableName]['environmentalFlow'] < 0,pcr.scalar(0))
	fractionMinimumReservedRechargeMap= pcr.ifthen(ncData[variableName]['environmentalFlow'] < 0,pcr.scalar(0))
	textFile= open(textFileName % environmentalFlowPercent,'w')
	hStr= 'Environmental flow analysis per basin, resulting in a map of renewable, exploitable recharge, for the %d%s quantile of discharge\n' % (environmentalFlowPercent,'%')
	hStr+= 'Returns Q_%d/R, the fraction of reserved recharge needed to sustain fully the environental flow requirement defined as the %d percentile,\n' % (environmentalFlowPercent, environmentalFlowPercent)
	hStr+= 'and Q*_%d/R, a reduced fraction that takes the availability of surface water into account\n' % environmentalFlowPercent
	textFile.write(hStr)
	print hStr
	# create header to display on screen and write to file
	# reported are: 1: ID, 2: Area, 3: average discharge, 4: environmental flow, 5: average recharge,
	# 6: Q_%d/Q, 7: Q_%d/R_Avg, 8: R_Avg/Q_Avg, 9: Q*_%d/R_Avg
	hStr= '%6s,%15s,%15s,%15s,%15s,%15s,%15s,%15s,%15s\n' % \
		('ID','Area [km2]','Q_Avg [m3]','Q_%d [m3]' % environmentalFlowPercent ,'R_Avg [m3]','Q_%d/Q_Avg [-]' % environmentalFlowPercent,\
			'Q_%d/Q_Avg [-]' % environmentalFlowPercent,'R_Avg/Q_Avg [-]','Q*_%d/Q_Avg [-]' % environmentalFlowPercent)
	textFile.write(hStr)
	print hStr
	for catchment in xrange(1,maximumCatchmentID+1):
		# create catchment mask and check whether it does not coincide with a lake
		catchmentMask= catchments == catchment
		catchmentSize= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,cellArea*1.e-6)),1)[0]
		#~ ##~ if pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,pcr.scalar(lakeMask))),1) <> \
				#~ ##~ pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,pcr.scalar(catchmentMask))),1)[0] and \
				#~ ##~ catchmentSize > catchmentSizeLimit:
		key= 'annualAverage'
		variableName= 'discharge'			
		if bool(pcr.cellvalue(pcr.maptotal(pcr.ifthen((ldd == 5) & catchmentMask,\
				pcr.scalar(ncData[variableName][key] > 0))),1)[0]) and catchmentSize >= catchmentSizeLimit:
			# valid catchment, process
			# all volumes are in m3 per year
			key= 'annualAverage'
			catchmentAverageDischarge= pcr.cellvalue(pcr.mapmaximum(pcr.ifthen(catchmentMask & (ldd == 5),\
				ncData[variableName][key])),1)[0]*365.25*3600*24
			variableName= 'gwRecharge'
			catchmentRecharge= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,ncData[variableName][key]*\
				(1.-fractionWater)*cellArea)),1)[0]
			variableName= 'totalRunoff'
			catchmentRunoff= pcr.cellvalue(pcr.maptotal(pcr.ifthen(catchmentMask,ncData[variableName][key]*\
				cellArea)),1)[0]
			key= 'environmentalFlow'
			variableName= 'discharge'			
			catchmentEnvironmentalFlow= pcr.cellvalue(pcr.mapmaximum(pcr.ifthen(catchmentMask & (ldd == 5),\
				ncData[variableName][key])),1)[0]*365.25*3600*24
			catchmentRunoff= max(catchmentRunoff,catchmentEnvironmentalFlow)
			if catchmentAverageDischarge > 0.:
				fractionEnvironmentalFlow= catchmentEnvironmentalFlow/catchmentAverageDischarge
				fractionGroundWaterContribution= catchmentRecharge/catchmentAverageDischarge
			else:
				fractionEnvironmentalFlow= 0.
				fractionGroundWaterContribution= 0.
			if catchmentRecharge > 0:
				fractionReservedRecharge= min(1,catchmentEnvironmentalFlow/catchmentRecharge)
			else:
				fractionReservedRecharge= 1.0
			fractionMinimumReservedRecharge= (fractionReservedRecharge+fractionGroundWaterContribution-\
				fractionReservedRecharge*fractionGroundWaterContribution)*fractionReservedRecharge
			#~ # echo to screen, and write to file and map
			wStr= '%6s,%15.1f,%15.6g,%15.6g,%15.6g,%15.6f,%15.6f,%15.6f,%15.6f\n' % \
				(catchment,catchmentSize,catchmentAverageDischarge,catchmentEnvironmentalFlow,catchmentRecharge,\
					fractionEnvironmentalFlow,fractionReservedRecharge,fractionGroundWaterContribution,fractionMinimumReservedRecharge)
			print wStr
			textFile.write(wStr)
			# update maps
			fractionReservedRechargeMap= pcr.ifthenelse(catchmentMask,\
				pcr.scalar(fractionReservedRecharge),fractionReservedRechargeMap)
			fractionMinimumReservedRechargeMap= pcr.ifthenelse(catchmentMask,\
				pcr.scalar(fractionMinimumReservedRecharge),fractionMinimumReservedRechargeMap)
	#-report map and close text file
	pcr.report(fractionReservedRechargeMap,fractionReservedRechargeMapFileName % environmentalFlowPercent)
	pcr.report(fractionMinimumReservedRechargeMap,fractionMinimumReservedRechargeMapFileName % environmentalFlowPercent)
	# close text file
	textFile.close()
	# finished
	print 'all done!'

if __name__ == '__main__':
	sys.exit(main())
	
