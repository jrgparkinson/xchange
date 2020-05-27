
function populateTradeWithSelect() {
    $.ajax({
        type: "GET",
        url: '/get_investors/',  // URL to your view that serves new info
        data: { "ignore_self": true }
    })
        .done(function (response) {
            console.log(response);
            if (response.error) {
                display_error(response.error);
            }

            $("#tradeWith option[value='X']").each(function () {
                if ($(this).value != "Open") {
                    $(this).remove();
                }
            });
            $.each(response.investors, function (i, item) {
                $('#tradeWith').append($('<option>', {
                    value: item.name,
                    text: item.name
                }));
            });
        });
}

function populateAthletes() {
    $.ajax({
        type: "GET",
        url: '/get_athletes/',  // URL to your view that serves new info
        data: {}
    })
        .done(function (response) {
            console.log(response);
            if (response.error) {
                display_error(response.error);
            }

            $("#athlete option").each(function () {
                $(this).remove();
            });

            $.each(response.athletes, function (i, athlete) {

                $('#athlete').append($('<option>', {
                    value: athlete.name,
                    text: athlete.name
                }));
            });
        });
}

function createShareFromModal() {
    var shareText = $("#athlete option:selected").val() + "/" + $("#volume").val();
    $("#commodityEntry").val(shareText);
}

function actionTrade(trade_id, change) {
    $.ajax({
        type: "GET",
        url: '/action_trade/',  // URL to your view that serves new info
        data: { "id": trade_id, "change": change }
    })
        .done(function (response) {
            console.log(response);
            if (response.error) {
                display_error(response.error);
            }

            if (window.location.href.includes("trades")) {
                reload_all();
            } else if (window.location.href.includes("athlete")) {
                reload_all_athlete_trades();
            }
        });
}

function reload_past_trades(investor_id) {
    //past_trades
    reload_trades("past_trades", false, investor_id);
}

function reload_active_trades() {
    reload_trades("active_trades", true);
}

function reload_trades(div, active, investor_id, other_opts) {


    var opts = {};
    if (!active) {
        opts["historical"] = true;
    }

    if (investor_id) {
        opts["investor_id"] = investor_id;
    }

    var athlete_filter = false;
    if (other_opts && "athlete" in other_opts) {
        opts["athlete_id"] = other_opts["athlete"];
        athlete_filter = true;
    }

    $.ajax({
        type: "GET",
        url: '/retrieve_trades/',  // URL to your view that serves new info
        data: opts
    })
        .done(function (response) {
            console.log(response)
            if (response.error) {
                // handle error
                console.log("error: " + response.error)
                return;
            }

            $("#" + div + " tbody tr.trade").remove();
            if (active) {
                $("tr.noTradesFound").show();
                //   $("tr.noTradesFound.buy").show();
            }

            // TODO: If historical, sort by last_updated
            if (response.trades == undefined) { return; }

            response.trades.forEach(trade => {
                console.log(trade);

                var com_label = format_asset(trade.asset);
                // if (trade.asset.athlete) {
                //   // this is a share
                //   com_label = "Share (" + trade.asset.athlete.name + ", " + trade.asset.volume + ")";
                // }



                var label;
                if (trade.type == "Sell") {

                    label = com_label + " selling ";

                    if (trade.buyer) {
                        label = label + "to " + trade.buyer.name;
                    }
                } else {
                    label = com_label + " buying ";
                    if (trade.seller && trade.seller != "") {
                        label = label + "from " + trade.seller.name;
                    }
                }
                label = label + " for " + trade.price;

                var closeAction = '<span data-toggle="tooltip" data-placement="left" title="Cancel/reject trade"><i class="fas fa-window-close fa-fw" onclick="actionTrade(' + trade.id + ', \'cancel\')"></i></span>';
                var acceptAction = '<span data-toggle="tooltip" data-placement="left" title="Accept trade"><i class="fas fa-check-circle fa-fw" onclick="actionTrade(' + trade.id + ', \'accept\')"></i></span>';

                var buyIcon = '<i class="fas fa-arrow-down fa-fw"></i>';
                var sellIcon = '<i class="fas fa-arrow-up fa-fw"></i>';

                var actions = "";
                if (trade.can_close) {
                    actions += closeAction;
                }
                // Can only action this if we're the buyer (these aren't open trades)
                if (trade.can_accept) {
                    actions += acceptAction;
                }

                // $("#active_trades").append("<li data-type='" + trade.type +"' data-id='"+trade.id+"'><div class='tradeLabel'>" + label +"</div><div class='tradeActions'>" + actions + "</div></li>")
                // if (trade.seller) { seller = format_investor_display(response.investor,trade.seller); } else { seller = 'Open'; }
                // if (trade.buyer) { buyer = format_investor_display(response.investor,trade.buyer); } else { buyer = 'Open'; }
                seller = format_investor_display(response.current_investor, trade.seller);
                buyer = format_investor_display(response.current_investor, trade.buyer);

                var trclass = "trade ";
                if (!athlete_filter) {
                    trclass += trade.type.toLowerCase() + ' ' + trade.status.toLowerCase()
                }

                var trade_athlete_id = "";
                if (trade.asset.athlete) {
                    trade_athlete_id = 'data-athlete="' + trade.asset.athlete.id + '"';
                }
                var newRow = '<tr class="trade ' + trclass + '" data-trade="' + trade.id + '" ' + trade_athlete_id + '>';

                var typeString = trade.type;
                if (trade.type == "Buy") { typeString = buyIcon + typeString; }
                if (trade.type == "Sell") { typeString = sellIcon + typeString; }
                if (active) {
                    // newRow += '<td>' + typeString + ' </td>';
                } else {
                    newRow += '<td>' + typeString + ' (' + trade.status + ') </td>';
                }

                var price_per_unit = "";
                if (trade.asset.volume) {
                    price_per_unit = " (" + Number(trade.price / trade.asset.volume).toFixed(2) + " per unit)";
                }
                if (athlete_filter) {
                    newRow += '<td>' + Number(trade.asset.volume).toFixed(2) + '</td>';
                } else {
                    newRow += '<td>' + com_label + '</td>';
                }
                newRow += '<td>' + trade.price + price_per_unit + '</td>';
                newRow += '<td>' + seller + '</td>';
                newRow += '<td>' + buyer + '</td>';
                newRow += '<td>' + format_investor_display(response.investor, trade.creator) + '</td>';

                if (active) {
                    newRow += '<td>' + actions + '</td></tr>';
                }
                else {
                    var d = new Date(trade.updated)
                    newRow += '<td>' + d.toLocaleString() + '</td></tr>';
                }

                // <th scope="col">Vol</th>
                // <th scope="col">Price</th>
                // <td scope="col">Seller</td>
                // <td scope="col">Buyer</td>
                // <td scope="col"></td>"
                // console.log(newRow);

                if (active && !athlete_filter) {
                    console.log("Append after");
                    if (trade.type == "Buy") {
                        $("#" + div + " tbody tr.buyHeader").after(newRow);
                        $("tr.noTradesFound.buy").hide();
                    } else {
                        $("#" + div + " tbody tr.sellHeader").after(newRow);
                        $("tr.noTradesFound.sell").hide();
                    }
                } else {
                    $("#" + div + " tbody").append(newRow);
                    $("#" + div + " tr.noTradesFound").hide();
                }
            });

        });
}

function format_investor_display(current_inv, inv) {
    if (!inv) {
        return "Open";
    }

    if (current_inv && inv && current_inv.name == inv.name) {
        return "You";
    } else {
        return '<a href="/investor/' + inv.id + '" class="badge badge-primary">' + inv.name + '</a>';
    }
}

function format_asset(asset) {
    if (asset.athlete) {
        // this is a share
        return 'Share (<a href="/athlete/' + asset.athlete.id + '" class="badge badge-danger">' + asset.athlete.name + '</a>, ' + Number(asset.volume).toFixed(2) + ')';
    } else {
        return "Unknown asset";
    }

}







function reload_all() {
    console.log("Refresh");
    // reload_past_trades();
    reload_active_trades();
    reload_past_trades();
    // reload_make_trades();
    //reload_outgoing_trades();
}



    //     	$(document.body).on('change','#trade_share_buy',function()
    //     		{
    //     				var runner_id = $('#trade_share_buy').find(":selected").val(); //$('#trade_share_buy option:selected').val();

    //     				console.log(runner_id);

    //     				console.log('Runner selected: ' + runner_id.toString());
    //     				update_investors_with_shares(runner_id);
    //     		});

//   });

//     function update_investors_with_shares(runner_id){


//         $.ajax({
//         	type: "GET",
//             url: {% url 'get_investors' %},  // URL to your view that serves new info
//             data: {'runner_id': runner_id}
//         })
//         .done(function(response) {

//             //$('#make_trade').html(response);

//             newOptions = response.investors;

//             console.log(response);
//             console.log(newOptions);

//             $('#seller_id_responsive option:gt(0)').remove(); // remove all options, but not the first 
//             var $el = $("#seller_id_responsive");

// $.each(newOptions, function(key,value) {

// 	var investor_id = value['investor_id'];

// 	// Skip currently logged in user
// 	var current_investor_id = {{request.user.investor.id}};
// 	if (investor_id != current_investor_id)
// 	{
// 	var txt = value['investor_name'] + " - " + value['num_shares'] + " share(s)";

//   $el.append($("<option></option>").attr("value", investor_id).text(txt));
// }
// });

//            // console.log(response);

//         });

//     }

