import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget, QGridLayout, QComboBox, QStackedWidget, QFrame
from models import ListModel, SinglePointModel
from datetime import datetime

class PlotWidget(pg.GraphicsView):
    """Wrapper around pyqtgraph's GraphicsView to create a live plot that automatically updates from connected models."""
    def __init__(self, x_axes:list[ListModel[datetime]], y_axes:list[ListModel[float]], y_axis_names:list[str], name:str = '', parent:QWidget = None):
        """x_axes - List containing multiple ListModels where each contains datetime objects to act as the x axis entries.\n
        y_axes - List containing multiple ListModels where each ListModel contains floats to act as the y axis entries.\n
        y_axis_names - List containing legend names to correspond to all y axes.
        """
        super().__init__(parent=parent)
        self._x_axes = x_axes
        self._y_axes = y_axes
        self._y_axis_names = y_axis_names
        if x_axes is not None:
            for ax in range(len(self._x_axes)):
                self._x_axes[ax].data_changed.connect(self._update_plot) #Ensure that the plot updates when the x axis changes.
        self._grid_opacity = 0.5
        self._colors = ["#e60049", "#0bb4ff", "#50e991", "#e6d800", "#9b19f5", "#dc0ab4", "#b3d4ff", "#00bfa0"] #Axis colors should be easily distinguishable and not jarring.
        self._plot_data_items: list[pg.PlotDataItem] = []
        self._legend_items:list[tuple[str,str]] = []
        self._hlines:list[tuple[str,SinglePointModel]] = []
        self._name = name

        #initialize the plot
        self._plot_layout = pg.GraphicsLayout()
        self.setCentralItem(self._plot_layout)
        self._plot = self._plot_layout.addPlot()
        date_axis = pg.DateAxisItem(orientation='bottom', utcOffset=datetime.now().utcoffset())
        self._plot.setAxisItems({'bottom':date_axis})
        self._plot.hideButtons()
        self._plot.addLegend()
        # self._plot.setMouseEnabled(x=False) #NOTE: This is left here to show how mouse can be enabled or disabled.
        self._plot.showGrid(y=True, alpha=self._grid_opacity)

        #load the plot data items
        if self._y_axes:
            if len(self._x_axes)==1:
                for y_axis, name, color in zip(self._y_axes, self._y_axis_names, self._colors):
                    data_item = pg.PlotDataItem(self._x_axes[0], y_axis, name=name, pen=pg.mkPen(color))
                    self._plot_data_items.append(data_item)
                    self._plot.addItem(data_item)
            elif len(self._x_axes) == len(self._y_axes):
                for x_axis, y_axis, name, color in zip(self._x_axes, self._y_axes, self._y_axis_names, self._colors):
                    data_item = pg.PlotDataItem(x_axis, y_axis, name=name, pen=pg.mkPen(color))
                    self._plot_data_items.append(data_item)
                    self._plot.addItem(data_item)

    @Slot()
    def _update_plot(self):
        if len(self._x_axes)==1:
            for y_axis, data_item in zip(self._y_axes, self._plot_data_items):
                x,y = self.verify_length(self._x_axes[0]._list.copy(), y_axis._list.copy())
                data_item.setData(x,y)
        elif len(self._x_axes) == len(self._y_axes):
            for x_axis, y_axis, data_item in zip(self._x_axes, self._y_axes, self._plot_data_items):
                x,y = self.verify_length(x_axis._list.copy(), y_axis._list.copy())
                data_item.setData(x,y)
        else:
            print('More than one X-axis, and not equal number of x and y-axis')

    def verify_length(self,x,y):
        a = len(x)
        b = len(y)
        if a==b:
            return x,y
        elif a == b+1:
            return x[1:],y
        elif a+1 == b:
            return x,y[1:]
        else:
            print('Plot vector lengths off by more than 1')


    def set_y_label(self, label:str = None):
        """Sets the label for the y axis."""
        self._plot.setLabel('left', label)

    def set_x_label(self, label:str = None):
        """Sets the label for the x axis."""
        self._plot.setLabel('bottom', label)

    def add_hline(self, color:str, model:SinglePointModel = None) -> pg.InfiniteLine:
        """Creates a horizonal line on the plot and returns the InfiniteLine object.\n
        color - The color of the line in the format '#rrggbb'.\n
        model - A SinglePointModel to update the position of the line. Will be ignored if model is not specified.
        """
        hline = pg.InfiniteLine(angle=0, pos=0, pen=pg.mkPen(color))
        hline.setMovable(False)
        self._plot.addItem(hline)
        if model is not None:
            model.data_changed.connect(lambda:hline.setValue(model.data))
        self._hlines.append((color,model))
        return hline
    
    def add_legend_item(self, color:str, name:str):
        """Adds an entry to the legend with the specified name and color. Will not affect the rest of the graph."""
        self._plot.legend.addItem(pg.PlotDataItem(pen=pg.mkPen(color)),name=name)
        self._legend_items.append((color, name))

    def copy(self, parent:QWidget = None):
        """Creates a copy of the PlotWidget that uses the same models.\n
        parent - Parent QWidget for the new copy.
        """
        copy = PlotWidget(self._x_axes, self._y_axes, self._y_axis_names, self._name, parent)
        for color, name in self._legend_items:
            copy.add_legend_item(color, name)
        for color, model in self._hlines:
            copy.add_hline(color, model)
        return copy

class MultiPlotWidget(QFrame):
    def __init__(self, parent:QWidget = None):
        super().__init__(parent=parent)

        self._init_UI()

    def _init_UI(self):
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(3)
        self.setMidLineWidth(3)

        self._layout = QGridLayout(self)
        self.setLayout(self._layout)
        self._layout.setColumnStretch(0,1)
        self._layout.setColumnStretch(1,1)
        self._layout.setColumnStretch(2,1)
        self._layout.setColumnStretch(3,1)
        self._layout.setRowStretch(1,1)
        self._layout.setRowStretch(2,1)

        self._plot_selector1 = QComboBox(self)
        self._plot_selector2 = QComboBox(self)
        self._plot_selector3 = QComboBox(self)
        self._plot_selector4 = QComboBox(self)
        self._layout.addWidget(self._plot_selector1,0,0,1,1)
        self._layout.addWidget(self._plot_selector2,0,1,1,1)
        self._layout.addWidget(self._plot_selector3,0,2,1,1)
        self._layout.addWidget(self._plot_selector4,0,3,1,1)

        self._plot_stack1 = QStackedWidget(self)
        self._plot_stack2 = QStackedWidget(self)
        self._plot_stack3 = QStackedWidget(self)
        self._plot_stack4 = QStackedWidget(self)
        self._layout.addWidget(self._plot_stack1,1,0,1,2)
        self._layout.addWidget(self._plot_stack2,1,2,1,2)
        self._layout.addWidget(self._plot_stack3,2,0,1,2)
        self._layout.addWidget(self._plot_stack4,2,2,1,2)

        self._plot_selector2.addItem('Off')
        self._plot_selector3.addItem('Off')
        self._plot_selector4.addItem('Off')
        self._plot_selector1.currentIndexChanged.connect(lambda:self._plot_stack1.setCurrentIndex(self._plot_selector1.currentIndex()))
        self._plot_selector2.currentIndexChanged.connect(lambda:self._plot_stack2.setCurrentIndex(self._plot_selector2.currentIndex()-1))
        self._plot_selector3.currentIndexChanged.connect(lambda:self._plot_stack3.setCurrentIndex(self._plot_selector3.currentIndex()-1))
        self._plot_selector4.currentIndexChanged.connect(lambda:self._plot_stack4.setCurrentIndex(self._plot_selector4.currentIndex()-1))
        self._plot_selector1.currentIndexChanged.connect(self._update_display)
        self._plot_selector2.currentIndexChanged.connect(self._update_display)
        self._plot_selector3.currentIndexChanged.connect(self._update_display)
        self._plot_selector4.currentIndexChanged.connect(self._update_display)

    def _update_display(self):
        if self._plot_selector2.currentIndex() == 0:
            self._plot_stack2.hide()
        else:
            self._plot_stack2.show()
            
        if self._plot_selector3.currentIndex() == 0:
            self._plot_stack3.hide()
        else:
            self._plot_stack3.show()
            
        if self._plot_selector4.currentIndex() == 0:
            self._plot_stack4.hide()
        else:
            self._plot_stack4.show()

        self._layout.removeWidget(self._plot_stack1)
        self._layout.removeWidget(self._plot_stack2)
        self._layout.removeWidget(self._plot_stack3)
        self._layout.removeWidget(self._plot_stack4)

        if self._plot_stack2.isVisible() and self._plot_stack3.isVisible() and self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,1,2)
            self._layout.addWidget(self._plot_stack2,1,2,1,2)
            self._layout.addWidget(self._plot_stack3,2,0,1,2)
            self._layout.addWidget(self._plot_stack4,2,2,1,2)

        elif self._plot_stack2.isVisible() and self._plot_stack3.isVisible() and not self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,1,2)
            self._layout.addWidget(self._plot_stack2,1,2,1,2)
            self._layout.addWidget(self._plot_stack3,2,0,1,4)

        elif self._plot_stack2.isVisible() and not self._plot_stack3.isVisible() and self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,1,2)
            self._layout.addWidget(self._plot_stack2,1,2,1,2)
            self._layout.addWidget(self._plot_stack4,2,0,1,4)

        elif self._plot_stack2.isVisible() and not self._plot_stack3.isVisible() and not self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,2,2)
            self._layout.addWidget(self._plot_stack2,1,2,2,2)

        elif not self._plot_stack2.isVisible() and self._plot_stack3.isVisible() and self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,1,4)
            self._layout.addWidget(self._plot_stack3,2,0,1,2)
            self._layout.addWidget(self._plot_stack4,2,2,1,2)

        elif not self._plot_stack2.isVisible() and self._plot_stack3.isVisible() and not self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,1,4)
            self._layout.addWidget(self._plot_stack3,2,0,1,4)

        elif not self._plot_stack2.isVisible() and not self._plot_stack3.isVisible() and self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,1,4)
            self._layout.addWidget(self._plot_stack4,2,0,1,4)

        elif not self._plot_stack2.isVisible() and not self._plot_stack3.isVisible() and not self._plot_stack4.isVisible():
            self._layout.addWidget(self._plot_stack1,1,0,4,4)

    def set_plots(self, plots:list[PlotWidget]):
        """Adds plots to the MultiPlotWidget.\n
        plots - list of plots to be added to the multi view.
        """
        for plot in plots:
            self._plot_selector1.addItem(plot._name)
            self._plot_selector2.addItem(plot._name)
            self._plot_selector3.addItem(plot._name)
            self._plot_selector4.addItem(plot._name)
            self._plot_stack1.addWidget(plot.copy(self))
            self._plot_stack2.addWidget(plot.copy(self))
            self._plot_stack3.addWidget(plot.copy(self))
            self._plot_stack4.addWidget(plot.copy(self))