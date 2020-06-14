
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

function populateAthletes(athleteSelectId, includeOwned) {
    if (includeOwned == undefined) { includeOwned = true; }
    else { includeOwned = false; }
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

            $("#" + athleteSelectId + " option").each(function () {
                $(this).remove();
            });

            $.each(response.athletes, function (i, athlete) {
                $('#' + athleteSelectId).append($('<option>', {
                    value: athlete.id,
                    text: athlete.name + (includeOwned ? " (owned: " + athlete.vol_owned + ")" : "")
                }));
            });

            // $()

            console.log("Set selected athlete: ");
            console.log($('#' + athleteSelectId + " option:first").val());
            $('#' + athleteSelectId).val($('#' + athleteSelectId + " option:first").val()).change();

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

            $("#" + selectId + " option").each(function () {
                $(this).remove();
            });

            // $('#'+selectId).append($('<option>', {
            //     value: "",
            //     text: "Select a contract",
            // }));
            $.each(response.contracts, function (i, contract) {

                $('#' + selectId).append($('<option>', {
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

function actionTrade(trade_id, change, confirmation) {
    var tr = $("tr[data-trade=" + trade_id + "]");

    if (change == "accept" && confirmation === undefined) {
        //display modal

        // populate modal
        var buy_sell = tr.attr("data-buy-sell");
        var type = tr.attr("data-asset-type");
        var max_shares = (type == "share") ? tr.attr("data-max-vol") : 0;

        var price_per_vol = (type == "share") ? tr.attr("data-price-per-vol") : 0;

        $("#confirmTitle").text("Confirm trade");
        $("#confirmButton").text(capitalizeFirstLetter(buy_sell));
        $("#confirmButton").attr("data-trade-id", trade_id);

        $(".confirm-body").hide();

        if (type == "share") {
            $(".confirm-share").show();
            // $(".confirm-share").text("max vol: " + max_shares);
            $("#confirmVolSlider").attr("max", max_shares);
            $("#confirmVolSlider").val(max_shares)
            $("#confirmVol").val(max_shares);
            $("#confirmPrice").attr("data-price-per-vol", price_per_vol);
            updatePrice();
        } else {
            $(".confirm-contract").show();
            $.ajax({
                type: "GET",
                url: DEPLOY_URL + 'get_contract/',
                data: { "trade_id": trade_id }
            })
                .done(function (response) {
                    console.log(response);
                    // var trade = response.trade;
                    var contract = response.contract;
                    // $(".confirm-contract").text(contract);


                    $("#contractTitle").text(capitalizeFirstLetter(contract.type) + " contract");

                    var obligation = "Unknown";
                    if (contract.type == "Future") {
                        var d = new Date(contract.strike_date); 
                        var asset = format_asset(contract.underlying);
                        obligation = "";
                        if (contract.seller) {
                            obligation += format_investor_display("", contract.seller) + " will sell ";
                        } else {
                            obligation += format_investor_display("", contract.buyer) + " will buy ";
                        }
                        obligation += asset + " for " + contract.strike_price;
                        obligation += " on " + d.toLocaleString();
                    } 
                    $("#contractObligation").html(obligation);
                    $("#contractPrice").text(response.trade.price);
                    $("#confirmButton").text("Enter contract");
                });
        }

        $('#confirmActionTrade').modal('show');

        return;
    }

    tr.addClass("actionedTrade");

    $.ajax({
        type: "GET",
        url: DEPLOY_URL + 'action_trade/',
        data: { "id": trade_id, "change": change, "confirmation": confirmation }
    })
        .done(function (response) {
            console.log(response)
            if (response.error) {
                display_error(response.error);
            } else {
                var trade = response.trade;

                if (change == "cancel") {
                    successNotif("Trade cancelled/rejected.");
                } else if (change == "accept") {
                    successNotif("Trade accepted.");
                } else {
                    successNotif("Action performed successfully.");
                }

                if (trade.status != "Pending") {
                    console.log("Remove row");

                    // var tr = $("tr[data-trade=" + trade_id + "]");
                    var myTable = tr.parent('tbody').parent('table'); //.DataTable();
                    if ($.fn.DataTable.isDataTable(myTable.attr('id'))) {
                        console.log("Remove datatable row with trade id: " + trade_id);
                        console.log(row);
                        var row = myTable.row(tr);

                        row.remove().draw();
                    } else {
                        console.log("Remove normal table row");
                        tr.remove();
                    }
                } else {
                    console.log("Update row, new volume=" + trade.asset.volume);
                    // update row
                    tr.find('td.volume').text(Number(trade.asset.volume).toFixed(2));
                    tr.attr("data-max-vol", Number(trade.asset.volume).toFixed(2));
                }

            }




            populate_top_bar_portfolio();
            tr.removeClass("actionedTrade");
        });
}

function reload_past_trades(investor_id) {
    //past_trades
    reload_trades("past_trades", false, investor_id);
}

function reload_active_trades() {
    reload_trades("active_trades", true);
}

function make_trade_row_attrs(trade) {
    var asset = trade.asset;

    var trade_athlete_id = "";
    var asset_type = "contract";
    if (asset.athlete) {
        asset_type = "share";
        trade_athlete_id = 'data-athlete="' + asset.athlete.id + '"';
    }
    var newRow = ' data-trade="' + trade.id + '" ' + trade_athlete_id;

    newRow += ' data-buy-sell="' + trade.type + '" ';
    newRow += ' data-asset-type="' + asset_type + '" ';
    newRow += ' data-max-vol="' + trade.asset.volume + '" ';
    newRow += ' data-price-per-vol="' + trade.price / trade.asset.volume + '" ';


    return newRow;
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
        if (response.trades == undefined || response.trades.length == 0) {
            console.log("No trades");
            $("tr.noTradesFound").show();
            return;
        }

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


            actions = get_actions(trade, trade.type);

            var buyIcon = ''; //'<i class="fas fa-arrow-down fa-fw"></i>';
            var sellIcon = ''; //'<i class="fas fa-arrow-up fa-fw"></i>';

            seller = format_investor_display(response.current_investor, trade.seller);
            buyer = format_investor_display(response.current_investor, trade.buyer);

            var trclass = "trade ";
            if (!athlete_filter) {
                trclass += trade.type.toLowerCase() + ' ' + trade.status.toLowerCase()
            }

            var trade_athlete_id = "";
            var asset_type = "contract";
            if (trade.asset.athlete) {
                asset_type = "share";
                trade_athlete_id = 'data-athlete="' + trade.asset.athlete.id + '"';
            }
            var newRow = '<tr class="trade ' + trclass + '"';

            // newRow += ' data-buy-sell="' + trade.type + '" ';
            // newRow += ' data-asset-type="' + asset_type + '" ';
            // newRow += ' data-max-vol="' + trade.asset.volume + '" ';
            newRow += make_trade_row_attrs(trade);
            newRow += '>';

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
                newRow += '<td class="volume">' + Number(trade.asset.volume).toFixed(2) + '</td>';
            } else {
                newRow += '<td>' + com_label + '</td>';
            }
            newRow += '<td>' + Number(trade.price).toFixed(2) + price_per_unit + '</td>';
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
                console.log("Append after " + trade.type);
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




