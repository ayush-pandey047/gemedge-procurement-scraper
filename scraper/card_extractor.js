() => {
    var results = [];
    var cards = document.querySelectorAll('div.card');
    cards.forEach(function(card) {
        if (!card) return;
        var text = card.innerText || '';
        if (!text) return;
        var bidLink = card.querySelector('a.bid_no_hover');
        var bid_id = bidLink ? bidLink.innerText.trim() : '';
        if (!bid_id) return;
        var allLinks = Array.from(card.querySelectorAll('a'));
        var result_url = '', ra_pdf_url = '', bid_doc_url = '';
        allLinks.forEach(function(a) {
            if (a.href.indexOf('getBidResultView') > -1) result_url = a.href;
            if (a.href.indexOf('showradocumentPdf') > -1) ra_pdf_url = a.href;
            if (a.href.indexOf('showbidDocument') > -1) bid_doc_url = a.href;
        });
        var lines = text.split('\n').map(function(l){ return l.trim(); }).filter(Boolean);
        function getField(label) {
            for (var i = 0; i < lines.length; i++) {
                if (lines[i].toLowerCase().indexOf(label.toLowerCase()) === 0) {
                    var val = lines[i].substring(label.length).replace(/^[:\s]+/, '').trim();
                    return val ? val : (lines[i+1] ? lines[i+1].trim() : '');
                }
            }
            return '';
        }
        var ministry = '', dept = '';
        for (var i = 0; i < lines.length; i++) {
            if (lines[i].toLowerCase().indexOf('department name and address') > -1) {
                ministry = lines[i+1] ? lines[i+1].trim() : '';
                var next2 = lines[i+2] ? lines[i+2].trim() : '';
                // Only use as dept if it doesn't look like a date line
                dept = (next2 && next2.toLowerCase().indexOf('start date') === -1) ? next2 : '';
                break;
            }
        }
        results.push({
            bid_id: bid_id,
            result_url: result_url,
            ra_pdf_url: ra_pdf_url,
            bid_doc_url: bid_doc_url,
            category: getField('Items'),
            buyer: ministry,
            department: dept,
            quantity: getField('Quantity'),
            bid_value: getField('Bid Value'),
            start_date: getField('Start Date'),
            award_date: getField('End Date'),
            status: getField('Status'),
            raw_text: text.substring(0, 500)
        });
    });
    return results;
}
