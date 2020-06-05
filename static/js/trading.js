
function populateTradeWithSelect() {
    $.ajax({
        type: "GET",
        url: DEPLOY_URL + 'get_investors/',  // URL to your view that serves new info
        data: { "ignore_self": true }
    })
        .done(function (response) {
            // console.log(response);
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

function populateAthletes(athleteSelectId) {
    $.ajax({
        type: "GET",
        url: DEPLOY_URL + 'get_athletes/',  // URL to your view that serves new info
        data: {}
    })
        .done(function (response) {
            // console.log(response);
            if (response.error) {
                display_error(response.error);
            }

            $("#" + athleteSelectId +" option").each(function () {
                $(this).remove();
            });

            $.each(response.athletes, function (i, athlete) {

                $('#'+athleteSelectId).append($('<option>', {
                    value: athlete.id,
                    text: athlete.name + " (owned: " + athlete.vol_owned + ")"
                }));
            });
        });
}

function populateExistingContracts(selectId) {
    $.ajax({
        type: "GET",
        url: DEPLOY_URL + 'get_investor_contracts/',  // URL to your view that serves new info
        data: {}
    })
        .done(function (response) {
            // console.log(response);
            if (response.error) {
                display_error(response.error);
            }

            $("#" + selectId +" option").each(function () {
                $(this).remove();
            });

            // $('#'+selectId).append($('<option>', {
            //     value: "",
            //     text: "Select a contract",
            // }));
            $.each(response.contracts, function (i, contract) {

                $('#'+selectId).append($('<option>', {
                    value: contract.id,
                    text: contract.pretty_print_long
                }));
            });
            setExistingContractDesc();
        });
}


function createShareFromModal() {
    var shareText = "Share: " + $("#athletesShare option:selected").text() + ", volume=" + $("#volume").val();
    $("#commodityEntry").val(shareText);

    // $("#commodityEntry").addClass("asset-share");
    $("#commodityEntry").attr("data-asset", "share");
    $("#commodityEntry").attr("data-athlete", $("#athletesShare option:selected").val());
    $("#commodityEntry").attr("data-volume", $("#volume").val());
}

function actionTrade(trade_id, change) {
    $("tr[data-trade=" + trade_id + "]").addClass("actionedTrade");

    $.ajax({
        type: "GET",
        url: DEPLOY_URL + 'action_trade/',  // URL to your view that serves new info
        data: { "id": trade_id, "change": change }
    })
        .done(function (response) {
            // console.log(response);
            if (response.error) {
                display_error(response.error);
                $("tr[data-trade=" + trade_id + "]").removeClass("actionedTrade");
                
            } else {

                if (change=="cancel") {
                    successNotif("Trade cancelled/rejected.");
                } else if (change == "accept") {
                    successNotif("Trade accepted.");
                } else {
                    successNotif("Action performed successfully.");
                }

                var myTable = $("tr[data-trade=" + trade_id + "]").parent('tbody').parent('table').DataTable();
                var tr = $("tr[data-trade=" + trade_id + "]");
                var row = myTable.row(tr);
                row.remove().draw();
            }
            
            
            
            // $("tr[data-trade=" + trade_id + "]").remove();
            

            // if (window.location.href.includes("trades")) {
            //     console.log("Reload for trades");
            //     reload_all();
            // } else if (window.location.href.includes("athlete")) {
            //     console.log("Reload for athletes");
            //     reload_all_athlete_trades();
            // } else if (window.location.href.includes("marketplace")) {
            //     console.log("Reload for marketplace");
            //     reload_marketplace_trades();
            // } else {
            //     console.log("Unknown post actionTrade ");
            // }

            populate_top_bar_portfolio();
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

    return $.ajax({
        type: "GET",
        url: DEPLOY_URL + 'retrieve_trades/',  // URL to your view that serves new info
        data: opts
    }).done(function (response) {
        console.log(response)
        if (response.error) {
            // handle error
            console.log("error: " + response.error)
            return;
        }

        $("#" + div + " tbody tr.trade").remove();
        // if (active && ) {
        //     $("tr.noTradesFound").show();
        //     //   $("tr.noTradesFound.buy").show();
        // }

        // TODO: If historical, sort by last_updated
        if (response.trades == undefined || response.trades.length==0) { 
            console.log("No trades"); 
            $("tr.noTradesFound").show();
            return; }

        response.trades.forEach(trade => {
            // console.log(trade);

            var com_label = format_asset(trade.asset, response.current_investor);

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



            actions = get_actions(trade);

            var buyIcon = ''; //'<i class="fas fa-arrow-down fa-fw"></i>';
            var sellIcon = ''; //'<i class="fas fa-arrow-up fa-fw"></i>';

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


        }); // end loop over trades

        console.log("Make datatable?");
        if (!active || athlete_filter) {
            console.log("Make datatable for table#" + div);

            var tab = $("table#" + div);
            console.log(tab);
            if ($.fn.DataTable.isDataTable(tab[0])) {
                tab.DataTable().destroy();
                console.log("Destroy datatable");
            }

            if (athlete_filter) {
                tab.dataTable({
                    paging: false,
                    scrollx: true,
                    order: [],
                    // "pageLength": 5,
                    // "scrollY": "300px",
                    // "scrollCollapse": true,
                });

            } else {
                tab.dataTable({
                    paging: false,
                    scrollx: true,
                    order: [],
                });
            }
        }
    });
}









function reload_all() {
    console.log("Refresh");
    // reload_past_trades();
    reload_active_trades();
    reload_past_trades();
    // reload_make_trades();
    //reload_outgoing_trades();
}




