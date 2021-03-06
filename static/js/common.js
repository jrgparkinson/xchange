// if (window.location.hostname.includes(".com")) {
//     var DEPLOY_URL='/xchange/';
// } else {
//     const DEPLOY_URL = '/';
// }

const DEPLOY_URL = window.location.hostname.includes(".com") ? "/xchange/" : "/";

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
        return '<span class="badgeContainer"><a href="' + DEPLOY_URL + 'investor/' + inv.id + '" class="badge badge-primary">' + inv.name + '</a></span>';
    }
}

function remove_row(tr) {
    var myTable = tr.parent('tbody').parent('table'); //.DataTable();
    if ($.fn.DataTable.isDataTable(myTable.attr('id'))) {
        console.log("Remove datatable row");
        // console.log(row);
        var row = myTable.row(tr);

        row.remove().draw();
    } else {
        console.log("Remove normal table row");
        tr.remove();
    }
}

function format_athlete(athlete) {
    return '<span class="badgeContainer"><a href="' + DEPLOY_URL + 'athlete/' + athlete.id + '" class="badge badge-danger">' + athlete.name + '</a></span>';
}

function format_asset(asset, current_inv) {
    if (asset.athlete) {
        // this is a share
        return 'Share (' + format_athlete(asset.athlete) + ', ' + Number(asset.volume).toFixed(2) + ')';
    } else if (asset.strike_price) {

        var x = "";
        if (asset.current_option) {
            // option
            x = "Option:<br>";
        } else {
            x = "Future:<br>";
        }

        var d = new Date(asset.strike_date);

        var underlying = "(" + format_athlete(asset.underlying.athlete) + ", " + Number(asset.underlying.volume).toFixed(2) + ')';

        var obl = "";
        if (asset.buyer) {
            obl = format_investor_display("", asset.buyer) + " to buy";
        } else {
            obl = format_investor_display("", asset.seller) + " to sell";
        }
        x += obl + ": " + underlying;
        x += "<br>Strike price: " + asset.strike_price + "<br>Strike date: " + d.toLocaleString();
        return x;
    } else {
        return "Unknown asset";
    }

}

function capitalizeFirstLetter(string) {
    // Thanks stackoverflow 
    // https://stackoverflow.com/questions/1026069/how-do-i-make-the-first-letter-of-a-string-uppercase-in-javascript
    return string.charAt(0).toUpperCase() + string.slice(1);
}

function get_actions(trade, trade_type) {
    var closeAction = '<button type="button" class="btn btn-danger" onclick="actionTrade(' + trade.id + ', \'cancel\')">Decline</button>';
    // var clas = trade_type.includes("ell") ? "success" : "info";
    var clas = "success";
    var acceptAction = ' <button type="button" class="btn btn-' + clas + '" onclick="actionTrade(' + trade.id + ', \'accept\')">' + capitalizeFirstLetter(trade_type) + '</button>';

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
            url: DEPLOY_URL + 'get_portfolio_value/', // URL to your view that serves new info
            data: {}
        })
        .done(function(response) {
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
            yAxes: [{
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
            }]
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
    if ($("#xzoom").prop('checked')) { zoom += 'x'; }
    if ($("#yzoom").prop('checked')) { zoom += 'y'; }
    console.log("zoom = " + zoom);
    chart.options.plugins.zoom.zoom.mode = zoom;
    chart.update();
}

$("input.zoom").change(updateZoom);

function successNotif(message) {
    $("#successNotifMsg").text(message);
    $('#successNotif').toast('show');
    // hide after 5 seconds
    setTimeout(function() { $('#successNotif').toast('hide'); }, 5000);
}
$(document).ready(function() {
    $("#datatables_crazyfix").remove();
    $('.toast').toast('hide');
});

function buySell(athlete_id, athlete_name) {

    $("#buySellShareTitle").html("Buy/sell shares in " + athlete_name);
    // $("#buySellShareBtn").html(buy_or_sell);

    $("#buySellShareBtn").attr('data-athlete', athlete_id);

    // Fill volume from existing table row if we can
    const volume = $(".buySellVolume[data-athlete=" + athlete_id + "]").val();
    console.log("Current volume is " + volume);
    $("input#volume").val(volume);

    table_row = $("tr[data-athlete=" + athlete_id + "]");
    $("input#price").val(table_row.find(".tradingAt").html());

    updateTotalBuySellPrice();

    $('#buySellShare').modal('show');
}

function buySellShare() {
    athlete = $("#buySellShareBtn").attr('data-athlete');
    volume = Number($("input#volume").val());
    price_per_vol = Number($("input#price").val());
    buy_sell = $('input[name=buysell]:checked').val();

    console.log("Make offer to " + buy_sell + " " + athlete + ": " + volume + "unit at " + price_per_vol + " per unit");

    $.ajax({
        type: "GET",
        url: '/create_trade/',
        data: {
            'data-asset': 'share',
            'tradeWith': 'Open',
            'price': price_per_vol * volume,
            'buysell': buy_sell,
            'data-athlete': athlete,
            'data-volume': volume,
        },
        success: function(data) {
            if (data.error) {
                display_error(data.error);
            } else {
                successNotif("Offer created succesfully.");
            }
            // reload_all();
        }
    });

}

function updateTotalBuySellPrice() {
    var total_price = Number($("input#volume").val()) * Number($("input#price").val());
    $("#totalPrice").html(total_price.toFixed(2));
}