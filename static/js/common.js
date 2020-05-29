function format_investor_display(current_inv, inv) {
    if (!inv) {
        return "Open";
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