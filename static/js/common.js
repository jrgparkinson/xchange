function format_investor_display(current_inv, inv) {
    if (!inv) {
        return "Open";
    }

    if (inv.name == "The Cowley Club Bank") {
        return inv.name;
    }

    if (current_inv && inv && current_inv.name == inv.name) {
        return "You";
    } else {
        return '<span class="badgeContainer"><a href="/investor/' + inv.id + '" class="badge badge-primary">' + inv.name + '</a></span>';
    }
}

function format_athlete(athlete) {
    return '<span class="badgeContainer"><a href="/athlete/' + athlete.id + '" class="badge badge-danger">' + athlete.name + '</a></span>';
}
function format_asset(asset) {
    if (asset.athlete) {
        // this is a share
        return 'Share (' + format_athlete(asset.athlete) + ', ' + Number(asset.volume).toFixed(2) + ')';
    } else {
        return "Unknown asset";
    }

}

function get_actions(trade) {
    var closeAction = '<span data-toggle="tooltip" data-placement="left" title="Cancel/reject trade"><i class="fas fa-window-close fa-fw" onclick="actionTrade(' + trade.id + ', \'cancel\')"></i></span>';
    var acceptAction = '<span data-toggle="tooltip" data-placement="left" title="Accept trade"><i class="fas fa-check-circle fa-fw" onclick="actionTrade(' + trade.id + ', \'accept\')"></i></span>';

    var actions = "";
    if (trade.can_close) {
        actions += closeAction;
    }
    // Can only action this if we're the buyer (these aren't open trades)
    if (trade.can_accept) {
        actions += acceptAction;
    }
    return actions;
}

function populate_top_bar_portfolio() {

    $.ajax({
        type: "GET",
        url: '/get_portfolio_value/',  // URL to your view that serves new info
        data: {}
    })
        .done(function (response) {
            if (response.capital && response.shares) {
                $("#investor_capital_top").text(Number(response.capital).toFixed(2));
                $("#investor_shares_top").text(Number(response.shares).toFixed(2));
            }
        });

}

function setupChartStyles() {

    var style = getComputedStyle(document.body);
    var primCol = style.getPropertyValue('--fg-1');
    var bgcol = style.getPropertyValue('--bg-4');
    // var chartCol = style.getPropertyValue('--chartColor');
    Chart.defaults.global.defaultFontColor = primCol;
    Chart.defaults.global.defaultColor = bgcol;
}

function defaultChartOptions(ylab) {
    var style = getComputedStyle(document.body);
    var primCol = style.getPropertyValue('--fg-1');
    var bgcol = style.getPropertyValue('--bg-4');
    // var chartCol = style.getPropertyValue('--chartColor');
    // Chart.defaults.global.defaultFontColor = primCol;
    // Chart.defaults.global.defaultColor = bgcol;

    return {
        maintainAspectRatio: false,
        scales: {
            xAxes: [{
                type: 'time',
                ticks: {
                    autoSkip: true,
                    maxTicksLimit: 10,
                },
                
                scaleLabel: {
                    display: true,
                    labelString: "Time"
                },
                gridLines: {
                    color: primCol,
                    zeroLineColor: primCol
                }
            }],
            yAxes: [
                {
                    scaleLabel: {
                        display: true,
                        labelString: ylab,
                    },
                    ticks: {
                        beginAtZero: true
                    },
                    gridLines: {
                        color: primCol,
                        zeroLineColor: primCol
                    }
                }
            ]
        },
        plugins: {
            zoom: {
                zoom: {
                    enabled: true,
                    mode: 'xy',
                    speed: 0.05
                },
                pan: {
                    enabled: true,
                }
            }
        }
    };
}


function updateZoom() {
    var zoom = '';
    if($("#xzoom").prop('checked')) { zoom += 'x'; }
    if($("#yzoom").prop('checked')) { zoom += 'y'; }
    console.log("zoom = " + zoom);
    chart.options.plugins.zoom.zoom.mode = zoom;
    chart.update();
}

$("input.zoom").change(updateZoom);


$(document).ready(function() {
    $("#datatables_crazyfix").remove();
});