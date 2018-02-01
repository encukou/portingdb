var chart = function(csvpath, colormap, key_order, expand) {
colorrange = ["#F0AD4E", "#8c6699", "#a65959",];
strokecolor = '#000';

var format = d3.time.format("%Y-%m-%d %H:%M:%S %Z");
var date_format = d3.time.format("%Y-%m-%d");
var month_format = d3.time.format("%b");

var margin = {top: 20, right: 60, bottom: 30, left: 60};
var width = 600;
var height = 600 - margin.top - margin.bottom;

var tooltip = d3.select("#chart-container")
    .append("div")
    .attr("class", "remove")
    .style("visibility", "hidden")
    .style('margin-left', '60px')
    ;

var x = d3.time.scale()
    .range([0, width]);

var y = d3.scale.linear()
    .range([height-10, 0]);

var z = d3.scale.ordinal()
    .range(colorrange);

// X Axis scale with year ticks
var xAxis = d3.svg.axis()
    .scale(x)
    .orient("bottom")
    .ticks(d3.time.years)
    .tickSize(20)
    .outerTickSize(0);

// X Axis scale with month ticks
var xAxisMonths = d3.svg.axis()
    .scale(x)
    .orient("bottom")
    .ticks(d3.time.months)
    .tickSize(5)
    .outerTickSize(0);

// Y Axis scale on the left
var yAxis = d3.svg.axis()
    .scale(y);

// Y Axis scale on the right
var yAxisr = d3.svg.axis()
    .scale(y);

var stack = d3.layout.stack()
    .offset(expand ? 'expand' : 'zero')
    .values(function(d) { return d.values; })
    .x(function(d) { return d.date; })
    .y(function(d) { return d.num_packages; });

var nest = d3.nest()
    .key(function(d) { return d.status; })
    .sortKeys(function (a, b) {
            return key_order.indexOf(a) - key_order.indexOf(b);
        } );

var area = d3.svg.area()
    .interpolate("cardinal")
    .x(function(d) { return x(d.date); })
    .y0(function(d) { return y(d.y0); })
    .y1(function(d) { return y(d.y0 + d.y); });

var svg = d3.select(".chart")
        .style("position", "relative")
  .append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
  .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

var graph = d3.csv(csvpath, function(data) {
  data.forEach(function(d) {
    d.date = format.parse(d.date);//.substr(0, 19));
    d.num_packages = +d.num_packages;
  });
  data = data.filter( function (d) { return d.date >= new Date(2015, 9, 10); } );

  // If the data spans less than years, we'll want to show month names on the X axis
  var year_span = data[data.length-1].date.getFullYear() - data[0].date.getFullYear();
  var show_months = (year_span < 2);

  var layers = stack(nest.entries(data));

  x.domain(d3.extent(data, function(d) { return d.date; }));
  y.domain([0, d3.max(data, function(d) { return d.y0 + d.y; })]);

  svg.selectAll(".layer")
      .data(layers)
    .enter().append("path")
      .attr("class", "layer")
      .attr("d", function(d) { return area(d.values); })
      .style("fill", function(d, i) { 
        return colormap[d.key];
      });


  svg.append("g")
      .attr("class", "x axis")
      .attr("transform", "translate(0," + height + ")")
      .call(xAxis)
  .selectAll("text")
    .attr("y", 6)
    .attr("x", 6)
    .style("text-anchor", "start")
    .text( function (d) { return d.getFullYear(); });

  svg.append("g")
      .attr("class", "x axis")
      .attr("transform", "translate(0," + height + ")")
      .call(xAxisMonths)
  .selectAll("text")
    .text( function (d) {
        // Only show month names if there's space (show_months),
        // and skip month name for January (d.getMonth() == 0)
        return show_months && d.getMonth() ? month_format(d) : "";
    });

  if (expand) {
    var y_format = function(d) { return d * 100 + '%'; };
  } else {
    var y_format = function(d) { return '' + d; };
  }

  svg.append("g")
      .attr("class", "y axis")
      .attr("transform", "translate(" + width + ", 0)")
      .call(yAxis.orient("right").tickFormat( y_format ));

  svg.append("g")
      .attr("class", "y axis")
      .call(yAxis.orient("left").tickFormat( y_format ));

  var make_minibadge = function (key) {
    return "<span style='background-color:" + colormap[key] + " !important;' class='minibadge'></span>&nbsp;";
  }
  var reset_tooltip = function () {
    var lines = ["&nbsp;"]
    key_order.forEach(function (key) {
      var p = make_minibadge(key);
      var text = key;
        lines.splice(1, 0, p + text);
    });
    tooltip.html( "<p>" + lines.join('<br>') + "</p>" ).style("visibility", "visible");
  };

  svg.selectAll(".layer")
    .attr("opacity", 1)
    .on("mouseover", function(d, i) {
      svg.selectAll(".layer").transition()
      .duration(250)
      .attr("opacity", function(d, j) {
        return j != i ? 1 : 1;
    })})

    .on("mousemove", function(dd, i) {
      var m=this;
      var lines = [];
      layers.forEach(function (d, i) {
      mousex = d3.mouse(m);
      mousex = mousex[0];
      var invertedx = x.invert(mousex);
      var selected = (d.values);
      for (var k = 0; k < selected.length; k++) {
        if (selected[k].date > invertedx) break;
        entry = selected[k];
        datearray[k] = selected[k].date;
      }

      pro = entry.num_packages;

      if (lines.length == 0) lines.push(date_format(entry.date));
      var p = make_minibadge(d.key);
      var text = d.key + ': ' + pro + " packages";
      if (dd === d) {
        lines.splice(1, 0, p + "<b>" + text + "</b>");
      } else { 
        lines.splice(1, 0, p + text);
      }
      });
      tooltip.html( "<p>" + lines.join('<br>') + "</p>" ).style("visibility", "visible");
    })
    .on("mouseout", function(d, i) {
      d3.select(this)
      .classed("hover", false)
       .attr("stroke-width", "0px");
      //reset_tooltip();
  })
    
  var vertical = d3.select(".chart")
        .append("div")
        .attr("class", "remove")
        .style("position", "absolute")
        .style("z-index", "19")
        .style("width", "1px")
        .style("height", "560px")
        .style("top", "10px")
        .style("bottom", "30px")
        .style("left", "0px")
        .style("opacity", "0.5")
        .style("background-color", "#fff");
//*
  d3.select(".chart")
      .on("mousemove", function(){  
         mousex = d3.mouse(this);
         mousex = mousex[0] + 5;
         vertical.style("left", mousex + "px" )})
      .on("mouseover", function(){  
         mousex = d3.mouse(this);
         mousex = mousex[0] + 5;
         vertical.style("left", mousex + "px")});
         //*/
  reset_tooltip();
});
}
