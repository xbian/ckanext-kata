this.ckan.module('dashboard', function ($, _) {
	return {
		initialize: function () {
			if ($('.new', this.el)) {
				setTimeout(function() {
					$('.masthead .notifications').removeClass('notifications-important').html('Notifications 0');
				}, 1000);
			}
		}
	};
});
