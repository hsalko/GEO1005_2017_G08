# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SpatialDecisionDockWidget
                                 A QGIS plugin
 This is a SDSS template for the GEO1005 course
                             -------------------
        begin                : 2015-11-02
        git sha              : $Format:%H$
        copyright            : (C) 2015 by Jorge Gil, TU Delft
        email                : j.a.lopesgil@tudelft.nl
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4 import QtGui, QtCore, uic
from qgis.core import *
from qgis.networkanalysis import *
import processing
# Initialize Qt resources from file resources.py
import resources

import os
import os.path
import random

from . import utility_functions as uf


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'spatial_decision_dockwidget_base.ui'))


class SpatialDecisionDockWidget(QtGui.QDockWidget, FORM_CLASS):

    closingPlugin = QtCore.pyqtSignal()
    #custom signals
    updateAttribute = QtCore.pyqtSignal(str)

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(SpatialDecisionDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        # define globals
        self.iface = iface
        self.canvas = self.iface.mapCanvas()

        # set up GUI operation signals
        # data
        self.iface.projectRead.connect(self.updateLayers)
        self.iface.newProjectCreated.connect(self.updateLayers)
        self.iface.legendInterface().itemRemoved.connect(self.updateLayers)
        self.iface.legendInterface().itemAdded.connect(self.updateLayers)
        self.openScenarioButton.clicked.connect(self.openScenario)
        self.saveScenarioButton.clicked.connect(self.saveScenario)
        self.selectLayerCombo.activated.connect(self.setSelectedLayer)
        self.selectAttributeCombo.activated.connect(self.setSelectedAttribute)

        # analysis
        self.graph = QgsGraph()
        self.tied_points = []
        self.setNetworkButton.clicked.connect(self.buildNetwork)
        self.shortestRouteButton.clicked.connect(self.calculateRoute)
        self.clearRouteButton.clicked.connect(self.deleteRoutes)
        self.serviceAreaButton.clicked.connect(self.calculateServiceArea)
        self.bufferButton.clicked.connect(self.calculateBuffer)
        self.selectBufferButton.clicked.connect(self.selectFeaturesBuffer)
        self.makeIntersectionButton.clicked.connect(self.calculateIntersection)
        self.selectRangeButton.clicked.connect(self.selectFeaturesRange)
        self.expressionSelectButton.clicked.connect(self.selectFeaturesExpression)
        self.expressionFilterButton.clicked.connect(self.filterFeaturesExpression)

        # visualisation
        self.displayStyleButton.clicked.connect(self.displayBenchmarkStyle)
        self.displayRangeButton.clicked.connect(self.displayContinuousStyle)

        # reporting
        self.featureCounterUpdateButton.clicked.connect(self.updateNumberFeatures)
        self.saveMapButton.clicked.connect(self.saveMap)
        self.saveMapPathButton.clicked.connect(self.selectFile)
        self.updateAttribute.connect(self.extractAttributeSummary)

        # set current UI restrictions


        # add button icons
        self.medicButton.setIcon(QtGui.QIcon(':icons/medic_box.png'))
        self.ambulanceButton.setIcon(QtGui.QIcon(':icons/ambulance.png'))


        # initialisation
        self.updateLayers()

        #run simple tests

    def closeEvent(self, event):
        # disconnect interface signals
        try:
            self.iface.projectRead.disconnect(self.updateLayers)
            self.iface.newProjectCreated.disconnect(self.updateLayers)
            self.iface.legendInterface().itemRemoved.disconnect(self.updateLayers)
            self.iface.legendInterface().itemAdded.disconnect(self.updateLayers)
        except:
            pass

        self.closingPlugin.emit()
        event.accept()

#######
#   Data functions
#######
    def openScenario(self,filename=""):
        scenario_open = False
        scenario_file = os.path.join('/Users/jorge/github/GEO1005','sample_data','time_test.qgs')
        # check if file exists
        if os.path.isfile(scenario_file):
            self.iface.addProject(scenario_file)
            scenario_open = True
        else:
            last_dir = uf.getLastDir("SDSS")
            new_file = QtGui.QFileDialog.getOpenFileName(self, "", last_dir, "(*.qgs)")
            if new_file:
                self.iface.addProject(new_file)
                scenario_open = True
        if scenario_open:
            self.updateLayers()

    def saveScenario(self):
        self.iface.actionSaveProject()

    def updateLayers(self):
        layers = uf.getLegendLayers(self.iface, 'all', 'all')
        self.selectLayerCombo.clear()
        if layers:
            layer_names = uf.getLayersListNames(layers)
            self.selectLayerCombo.addItems(layer_names)
            self.setSelectedLayer()
        else:
            self.selectAttributeCombo.clear()

    def setSelectedLayer(self):
        layer_name = self.selectLayerCombo.currentText()
        layer = uf.getLegendLayerByName(self.iface,layer_name)
        self.updateAttributes(layer)

    def getSelectedLayer(self):
        layer_name = self.selectLayerCombo.currentText()
        layer = uf.getLegendLayerByName(self.iface,layer_name)
        return layer

    def updateAttributes(self, layer):
        self.selectAttributeCombo.clear()
        if layer:
            fields = uf.getFieldNames(layer)
            self.selectAttributeCombo.addItems(fields)
            # send list to the report list window
            self.clearReport()
            self.updateReport(fields)

    def setSelectedAttribute(self):
        field_name = self.selectAttributeCombo.currentText()
        self.updateAttribute.emit(field_name)

    def getSelectedAttribute(self):
        field_name = self.selectAttributeCombo.currentText()
        return field_name

#######
#    Analysis functions
#######
    # route functions
    def getNetwork(self):
        roads_layer = self.getSelectedLayer()
        if roads_layer:
            # see if there is an obstacles layer to subtract roads from the network
            obstacles_layer = uf.getLegendLayerByName(self.iface, "Obstacles")
            if obstacles_layer:
                # retrieve roads outside obstacles (inside = False)
                features = uf.getFeaturesByIntersection(roads_layer, obstacles_layer, False)
                # add these roads to a new temporary layer
                road_network = uf.createTempLayer('Temp_Network','LINESTRING',roads_layer.crs().postgisSrid(),[],[])
                road_network.dataProvider().addFeatures(features)
            else:
                road_network = roads_layer
            return road_network
        else:
            return

    def buildNetwork(self):
        self.network_layer = self.getNetwork()
        if self.network_layer:
            # get the points to be used as origin and destination
            # in this case gets the centroid of the selected features
            selected_sources = self.getSelectedLayer().selectedFeatures()
            source_points = [feature.geometry().centroid().asPoint() for feature in selected_sources]
            # build the graph including these points
            if len(source_points) > 1:
                self.graph, self.tied_points = uf.makeUndirectedGraph(self.network_layer, source_points)
                # the tied points are the new source_points on the graph
                if self.graph and self.tied_points:
                    text = "network is built for %s points" % len(self.tied_points)
                    self.insertReport(text)
        return

    def calculateRoute(self):
        # origin and destination must be in the set of tied_points
        options = len(self.tied_points)
        if options > 1:
            # origin and destination are given as an index in the tied_points list
            origin = 0
            destination = random.randint(1,options-1)
            # calculate the shortest path for the given origin and destination
            path = uf.calculateRouteDijkstra(self.graph, self.tied_points, origin, destination)
            # store the route results in temporary layer called "Routes"
            routes_layer = uf.getLegendLayerByName(self.iface, "Routes")
            # create one if it doesn't exist
            if not routes_layer:
                attribs = ['id']
                types = [QtCore.QVariant.String]
                routes_layer = uf.createTempLayer('Routes','LINESTRING',self.network_layer.crs().postgisSrid(), attribs, types)
                uf.loadTempLayer(routes_layer)
            # insert route line
            uf.insertTempFeatures(routes_layer, [path], [['testing',100.00]])
            self.refreshCanvas(routes_layer)

    def deleteRoutes(self):
        routes_layer = uf.getLegendLayerByName(self.iface, "Routes")
        if routes_layer:
            ids = uf.getAllFeatureIds(routes_layer)
            routes_layer.startEditing()
            for id in ids:
                routes_layer.deleteFeature(id)
            routes_layer.commitChanges()

    def getServiceAreaCutoff(self):
        cutoff = self.serviceAreaCutoffEdit.text()
        if uf.isNumeric(cutoff):
            return uf.convertNumeric(cutoff)
        else:
            return 0

    def calculateServiceArea(self):
        options = len(self.tied_points)
        if options > 0:
            # origin is given as an index in the tied_points list
            origin = random.randint(1,options-1)
            cutoff_distance = self.getServiceAreaCutoff()
            if cutoff_distance == 0:
                return
            service_area = uf.calculateServiceArea(self.graph, self.tied_points, origin, cutoff_distance)
            # store the service area results in temporary layer called "Service_Area"
            area_layer = uf.getLegendLayerByName(self.iface, "Service_Area")
            # create one if it doesn't exist
            if not area_layer:
                attribs = ['cost']
                types = [QtCore.QVariant.Double]
                area_layer = uf.createTempLayer('Service_Area','POINT',self.network_layer.crs().postgisSrid(), attribs, types)
                uf.loadTempLayer(area_layer)
            # insert service area points
            geoms = []
            values = []
            for point in service_area.itervalues():
                # each point is a tuple with geometry and cost
                geoms.append(point[0])
                # in the case of values, it expects a list of multiple values in each item - list of lists
                values.append([cutoff_distance])
            uf.insertTempFeatures(area_layer, geoms, values)
            self.refreshCanvas(area_layer)

    # buffer functions
    def getBufferCutoff(self):
        cutoff = self.bufferCutoffEdit.text()
        if uf.isNumeric(cutoff):
            return uf.convertNumeric(cutoff)
        else:
            return 0

    def calculateBuffer(self):
        origins = self.getSelectedLayer().selectedFeatures()
        layer = self.getSelectedLayer()
        if origins > 0:
            cutoff_distance = self.getBufferCutoff()
            buffers = {}
            for point in origins:
                geom = point.geometry()
                buffers[point.id()] = geom.buffer(cutoff_distance,12).asPolygon()
            # store the buffer results in temporary layer called "Buffers"
            buffer_layer = uf.getLegendLayerByName(self.iface, "Buffers")
            # create one if it doesn't exist
            if not buffer_layer:
                attribs = ['id', 'distance']
                types = [QtCore.QVariant.String, QtCore.QVariant.Double]
                buffer_layer = uf.createTempLayer('Buffers','POLYGON',layer.crs().postgisSrid(), attribs, types)
                uf.loadTempLayer(buffer_layer)
            # insert buffer polygons
            geoms = []
            values = []
            for buffer in buffers.iteritems():
                # each buffer has an id and a geometry
                geoms.append(buffer[1])
                # in the case of values, it expects a list of multiple values in each item - list of lists
                values.append([buffer[0],cutoff_distance])
            uf.insertTempFeatures(buffer_layer, geoms, values)
            self.refreshCanvas(buffer_layer)

    def calculateIntersection(self):
        # use the buffer to cut from another layer
        cutter = uf.getLegendLayerByName(self.iface, "Buffers")
        # use the selected layer for cutting
        layer = self.getSelectedLayer()
        if cutter.featureCount() > 0:
            # get the intersections between the two layers
            intersection = processing.runandload('qgis:intersection',layer,cutter,None)
            intersection_layer = uf.getLegendLayerByName(self.iface, "Intersection")
            # prepare results layer
            save_path = "%s/dissolve_results.shp" % QgsProject.instance().homePath()
            # dissolve grouping by origin id
            dissolve = processing.runandload('qgis:dissolve',intersection_layer,False,'id',save_path)
            dissolved_layer = uf.getLegendLayerByName(self.iface, "Dissolved")
            # close intersections intermediary layer
            QgsMapLayerRegistry.instance().removeMapLayers([intersection_layer.id()])

            # add an 'area' field and calculate
            # functiona can add more than one filed, therefore names and types are lists
            uf.addFields(dissolved_layer, ["area"], [QtCore.QVariant.Double])
            uf.updateField(dissolved_layer, "area","$area")

    # after adding features to layers needs a refresh (sometimes)
    def refreshCanvas(self, layer):
        if self.canvas.isCachingEnabled():
            layer.setCacheImage(None)
        else:
            self.canvas.refresh()

    # feature selection
    def selectFeaturesBuffer(self):
        layer = self.getSelectedLayer()
        buffer_layer = uf.getLegendLayerByName(self.iface, "Buffers")
        if buffer_layer and layer:
            uf.selectFeaturesByIntersection(layer, buffer_layer, True)

    def selectFeaturesRange(self):
        layer = self.getSelectedLayer()
        # for the range takes values from the service area (max) and buffer (min) text edits
        max = self.getServiceAreaCutoff()
        min = self.getBufferCutoff()
        if layer and max and min:
            # gets list of numeric fields in layer
            fields = uf.getNumericFields(layer)
            if fields:
                # selects features with values in the range
                uf.selectFeaturesByRangeValues(layer, fields[0].name(), min, max)

    def selectFeaturesExpression(self):
        layer = self.getSelectedLayer()
        uf.selectFeaturesByExpression(layer, self.expressionEdit.text())

    def filterFeaturesExpression(self):
        layer = self.getSelectedLayer()
        uf.filterFeaturesByExpression(layer, self.expressionEdit.text())


#######
#    Visualisation functions
#######
    def displayBenchmarkStyle(self):
        # loads a predefined style on a layer.
        # Best for simple, rule based styles, and categorical variables
        # attributes and values classes are hard coded in the style
        layer = uf.getLegendLayerByName(self.iface, "Obstacles")
        path = "%s/styles/" % QgsProject.instance().homePath()
        # load a categorical style
        layer.loadNamedStyle("%sobstacle_danger.qml" % path)
        layer.triggerRepaint()
        self.iface.legendInterface().refreshLayerSymbology(layer)
        
        # load a simple style
        layer = uf.getLegendLayerByName(self.iface, "Buffers")
        layer.loadNamedStyle("%sbuffer.qml" % path)
        layer.triggerRepaint()
        self.iface.legendInterface().refreshLayerSymbology(layer)
        self.canvas.refresh()

    def displayContinuousStyle(self):
        # produces a new symbology renderer for graduated style
        layer = self.getSelectedLayer()
        attribute = self.getSelectedAttribute()
        # define several display parameters
        display_settings = {}
        # define the interval type and number of intervals
        # EqualInterval = 0; Quantile  = 1; Jenks = 2; StdDev = 3; Pretty = 4;
        display_settings['interval_type'] = 1
        display_settings['intervals'] = 10
        # define the line width
        display_settings['line_width'] = 0.5
        # define the colour ramp
        # the ramp's bottom and top colour. These are RGB tuples that can be edited
        ramp = QgsVectorGradientColorRampV2(QtGui.QColor(0, 0, 255, 255), QtGui.QColor(255, 0, 0, 255), False)
        # any other stops for intermediate colours for greater control. can be edited or skipped
        ramp.setStops([QgsGradientStop(0.25, QtGui.QColor(0, 255, 255, 255)),
                       QgsGradientStop(0.5, QtGui.QColor(0,255,0,255)),
                       QgsGradientStop(0.75, QtGui.QColor(255, 255, 0, 255))])
        display_settings['ramp'] = ramp
        # call the update renderer function
        renderer = uf.updateRenderer(layer, attribute, display_settings)
        # update the canvas
        if renderer:
            layer.setRendererV2(renderer)
            layer.triggerRepaint()
            self.iface.legendInterface().refreshLayerSymbology(layer)
            self.canvas.refresh()

#######
#    Reporting functions
#######
    # update a text edit field
    def updateNumberFeatures(self):
        layer = self.getSelectedLayer()
        if layer:
            count = layer.featureCount()
            self.featureCounterEdit.setText(str(count))

    # selecting a file for saving
    def selectFile(self):
        last_dir = uf.getLastDir("SDSS")
        path = QtGui.QFileDialog.getSaveFileName(self, "Save map file", last_dir, "PNG (*.png)")
        if path.strip()!="":
            path = unicode(path)
            uf.setLastDir(path,"SDSS")
            self.saveMapPathEdit.setText(path)

    # saving the current screen
    def saveMap(self):
        filename = self.saveMapPathEdit.text()
        if filename != '':
            self.canvas.saveAsImage(filename,None,"PNG")

    def extractAttributeSummary(self, attribute):
        # get summary of the attribute
        summary = []
        layer = self.getSelectedLayer()

        # send this to the table
        self.clearTable()
        self.updateTable(summary)

    # report window functions
    def updateReport(self,report):
        self.reportList.clear()
        self.reportList.addItems(report)

    def insertReport(self,item):
        self.reportList.insertItem(0, item)

    def clearReport(self):
        self.reportList.clear()

    # table window functions
    def updateTable(self, values):
        # takes a list of label / value pairs, can be tuples or lists. not dictionaries to control order
        self.statisticsTable.setHorizontalHeaderLabels(["Item","Value"])
        self.statisticsTable.setRowCount(len(values))
        for i, item in enumerate(values):
            self.statisticsTable.setItem(i,0,QtGui.QTableWidgetItem(str(item[0])))
            self.statisticsTable.setItem(i,1,QtGui.QTableWidgetItem(str(item[1])))
        self.statisticsTable.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        self.statisticsTable.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.Stretch)
        self.statisticsTable.resizeRowsToContents()

    def clearTable(self):
        self.statisticsTable.clear()
